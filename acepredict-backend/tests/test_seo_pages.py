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
    assert pg.snapshot["pct1"] > 80 and pg.snapshot["raw1"] <= pg.snapshot["pct1"]
    assert 70 <= pg.snapshot["pct1"] <= 98
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
    assert "Match prévu le" in h
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


def test_display_pct_matches_app_formula():
    assert seo_pages.display_pct(50) == 70.0
    assert seo_pages.display_pct(99) == 98.0
    assert seo_pages.display_pct(81.1) == 87.8


def test_old_snapshot_is_converted_once(seeded):
    db = TestingSessionLocal()
    pg = db.query(models.MatchPage).one()
    snap = dict(pg.snapshot)
    snap["pct1"], snap["pct2"] = 81.1, 18.9
    snap.pop("raw1"); snap.pop("raw2")
    pg.snapshot = snap; db.commit()
    seo_pages.enrich_snapshots(db)
    db.refresh(pg)
    assert pg.snapshot["pct1"] == 87.8 and pg.snapshot["raw1"] == 81.1
    assert seo_pages.enrich_snapshots(db) == 0
    db.close()


def test_evergreen_tournament_players_and_day_pages(seeded):
    from app.services import seo_extra
    assert seo_extra.evergreen_for("Shanghai") == "shanghai"
    assert seo_extra.evergreen_for("Masters de Paris-Bercy") == "paris-bercy"
    assert seo_extra.evergreen_for("Jerome Open") is None
    r = client.get("/seo/fr/tournoi/shanghai")
    assert r.status_code == 200 and "Pronostics Masters de Shanghai" in r.text and "FAQPage" in r.text
    assert "Alexander Zverev" in r.text  # favoris par Elo de surface
    assert client.get("/seo/fr/tournoi/roland-garros").status_code == 200
    assert client.get("/seo/fr/tournois").status_code == 200
    j = client.get("/seo/fr/joueurs")
    assert "alexander-zverev" in j.text
    p = client.get("/seo/fr/joueur/alexander-zverev")
    assert p.status_code == 200 and "Pronostic Alexander Zverev" in p.text and "ProfilePage" in p.text
    assert client.get("/seo/fr/joueur/inconnu").status_code == 404
    assert client.get("/seo/fr/pronostics/aujourdhui").status_code == 200
    assert client.get("/seo/fr/pronostics/hier").status_code == 404
    sm = client.get("/seo/sitemap.xml").text
    assert "/fr/joueur/alexander-zverev" in sm and "/fr/tournoi/roland-garros" in sm


def test_match_page_links_to_player_and_tournament(seeded):
    db = TestingSessionLocal()
    slug = db.query(models.MatchPage).one().slug
    db.close()
    h = client.get(f"/seo/fr/pronostic/{slug}").text
    assert "/fr/joueur/alexander-zverev" in h and "Pour aller plus loin" in h


def test_finals_section_on_tournament_pages(seeded):
    db = TestingSessionLocal()
    pg = db.query(models.MatchPage).one()
    snap = dict(pg.snapshot); snap["round_label"] = "finale"; pg.snapshot = snap; db.commit()
    db.close()
    assert "Phases finales : pronostics et résultats" in client.get("/seo/fr/tournoi/shanghai").text
    ts = TestingSessionLocal().query(models.MatchPage).one().tournament_slug
    h = client.get(f"/seo/fr/tournoi/{ts}").text
    assert "Phases finales" in h and "Finale" in h


def test_retro_big_matches_are_clickable_pages_and_not_in_bilan(seeded):
    from app.services import seo_extra
    db = TestingSessionLocal()
    a, b, when = seeded
    comp = models.Competition(name="Shanghai Masters", category="masters_1000", tour="atp", surface="hard", season=when.year)
    db.add(comp); db.commit()
    db.add(models.Match(player1_id=b, player2_id=a, winner_id=b, score="7-6 6-4", round="F", competition_id=comp.id,
                        tourney_date=datetime.utcnow() - timedelta(days=20), surface="hard"))
    db.commit()
    before = seo_pages.accuracy(db)
    assert seo_extra.sync_retro_pages(db) == 1
    assert seo_extra.sync_retro_pages(db) == 0
    assert seo_pages.accuracy(db) == before  # l'analyse rétrospective n'entre jamais dans le bilan
    slug = db.query(models.MatchPage).filter(models.MatchPage.match_key.like("retro|%")).one().slug
    db.close()
    h = client.get("/seo/fr/tournoi/shanghai").text
    assert "analyse et résultat" in h and f"/fr/pronostic/{slug}" in h
    page = client.get(f"/seo/fr/pronostic/{slug}").text
    assert "Analyse juste" in page or "Analyse ratée" in page
    assert "SportsEvent" not in page and "7-6 6-4" in page
    assert slug not in client.get("/seo/fr/pronostics").text  # absent des listes de pronostics en direct


def test_evergreen_shows_matches_before_intro_and_photo_cache(seeded):
    h = client.get("/seo/fr/tournoi/shanghai").text
    assert h.index("analyse et résultat") < h.index("Le tournoi en bref")
    db = TestingSessionLocal()
    a, b, when = seeded
    pl = db.get(models.Player, a)
    assert seo_pages.photo_for(db, pl) == seo_pages.PLACEHOLDER_IMG  # fetch_photo stubbé -> None, mis en cache
    assert db.get(models.PlayerPhoto, str(a)) is not None
    db.close()


def test_empty_evergreen_shows_next_predictions(seeded):
    h = client.get("/seo/fr/tournoi/roland-garros").text
    assert "Aucun match de Roland-Garros" in h and "Prochains pronostics" in h and "/fr/pronostic/" in h
