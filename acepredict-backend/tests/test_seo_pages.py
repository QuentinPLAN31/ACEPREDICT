"""Pages SEO par match : création, snapshot figé, résultat, routes."""
import os
from datetime import datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app import models
from app.services import seo_pages, seo_render

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _db_and_no_network(monkeypatch):
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(seo_pages, "fetch_photo", lambda name: None)
    monkeypatch.setattr(seo_pages, "ping_indexnow", lambda urls: False)
    yield
    if previous is not None:
        app.dependency_overrides[get_db] = previous
    else:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="module")
def seeded():
    db = TestingSessionLocal()
    a = models.Player(name="Alexander Zverev", country="GER", tour="atp", elo_overall=1900, elo_hard=1950,
                      data_confidence=models.DataConfidenceEnum.high, current_rank=3)
    b = models.Player(name="Quentin Halys", country="FRA", tour="atp", elo_overall=1600, elo_hard=1620,
                      data_confidence=models.DataConfidenceEnum.high, current_rank=58)
    ghost = models.Player(name="Inconnu", tour="atp", data_confidence=models.DataConfidenceEnum.insufficient)
    db.add_all([a, b, ghost]); db.commit()
    when = datetime.utcnow() + timedelta(hours=5)
    fx = models.Fixture(external_id="x1", player1_id=a.id, player2_id=b.id, tour="atp", surface="hard",
                        indoor=True, round="R32", tournament_name="Masters de Shanghai",
                        tournament_id_external="shanghai", city="Shanghai", scheduled_time=when)
    fx2 = models.Fixture(external_id="x2", player1_id=a.id, player2_id=ghost.id, tour="atp", surface="hard",
                         round="R32", tournament_name="Masters de Shanghai", scheduled_time=when)
    db.add_all([fx, fx2]); db.commit()
    ids = (a.id, b.id, when)
    db.close()
    return ids


def test_create_page_and_idempotent(seeded):
    db = TestingSessionLocal()
    st = seo_pages.sync_match_pages(db)
    assert st["created"] == 1 and st["skipped"] == 1 and st["errors"] == 0
    again = seo_pages.sync_match_pages(db)
    assert again["created"] == 0
    pg = db.query(models.MatchPage).one()
    assert pg.slug.startswith("alexander-zverev-quentin-halys-shanghai-")
    assert pg.snapshot["pct1"] > 80
    db.close()


def test_page_route_before_and_no_fake_data(seeded):
    db = TestingSessionLocal()
    slug = db.query(models.MatchPage).one().slug
    db.close()
    r = client.get(f"/seo/fr/pronostic/{slug}")
    assert r.status_code == 200
    h = r.text
    assert "Pronostic Alexander Zverev – Quentin Halys" in h
    assert 'rel="canonical"' in h and "FAQPage" in h and "SportsEvent" in h
    assert "Cette page affichera le résultat réel" in h
    assert "Court couvert" in h  # fixture indoor -> section météo couverte
    assert "Elo" not in h


def test_result_attached_and_after_state(seeded):
    db = TestingSessionLocal()
    a, b, when = seeded
    db.add(models.Match(player1_id=a, player2_id=b, winner_id=a, score="6-4 6-3", tourney_date=when - timedelta(days=1),
                        created_at=when + timedelta(hours=8)))
    db.commit()
    done = seo_pages.attach_results(db, now=when + timedelta(hours=10))
    assert len(done) == 1
    pg = db.query(models.MatchPage).one()
    assert pg.result_score == "6-4 6-3"
    assert seo_pages.accuracy(db)["ok"] == 1
    slug = pg.slug
    db.close()
    h = client.get(f"/seo/fr/pronostic/{slug}").text
    assert "Pronostic juste" in h and "Résultat final" in h


def test_hub_bilan_tournoi_sitemap(seeded):
    assert client.get("/seo/fr/pronostics").status_code == 200
    assert "100" in client.get("/seo/fr/bilan").text
    db = TestingSessionLocal()
    ts = db.query(models.MatchPage).one().tournament_slug
    db.close()
    assert client.get(f"/seo/fr/tournoi/{ts}").status_code == 200
    sm = client.get("/seo/sitemap.xml")
    assert "<urlset" in sm.text and "/fr/pronostic/" in sm.text
    assert client.get("/seo/fr/pronostic/nope").status_code == 404


def test_render_edge_cases():
    d = dict(img1="", img2="", p1="A", p2="B", pct1=55.0, pct2=45.0, rank1="", rank2="", tournoi="T", round="Finale",
             tour_lbl="ATP", surface="clay", ville="X", date_court="1 janv. 2026", date_long="jeudi 1 janvier 2026",
             heure="10:00", iso="2026-01-01T10:00:00+01:00", slug="a-b", publie="1 janvier 2026",
             publie_iso="2026-01-01T00:00:00Z", modif_iso="2026-01-01T00:00:00Z", st={}, analyse=["x"], related=[],
             best_of=5, scores=[], wx=None, traits={}, tournoi_slug="t", winner="B", score="6-4 RET", actual={"sets": "—"})
    assert "Finale" in seo_render.render(d, "before")
    assert "Pronostic raté" in seo_render.render(d, "after")


def test_hub_has_past_button_date_separators_and_portraits(seeded):
    h = client.get("/seo/fr/pronostics").text
    assert "Voir les matchs passés" in h
    assert 'class="dh"' in h and 'class="mrow"' in h and "<img" in h


def test_more_stats_rows_when_data_exists(seeded):
    db = TestingSessionLocal()
    a, b, when = seeded
    pa = db.get(models.Player, a); pa.height_cm = 198; pa.hand = "R"; pa.birthdate = datetime(1997, 4, 22)
    db.commit()
    pg = db.query(models.MatchPage).one()
    snap = dict(pg.snapshot); snap.pop("bio", None); pg.snapshot = snap; pg.finished_at = None; db.commit()
    assert seo_pages.enrich_snapshots(db) == 1
    db.refresh(pg)
    d, _ = seo_pages.build_context(db, pg)
    assert d["st"]["taille"][0] == 198 and d["st"]["main"][0] == "Droitier"
    assert "198 cm" in seo_render.render(d, "before")
    db.close()
