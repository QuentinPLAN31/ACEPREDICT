"""
Tests de scripts/sync_daily.py :: run() — téléchargement CSV mocké (httpx.get),
jamais de vrai appel réseau. Vérifie la dégradation gracieuse fichier par
fichier et l'idempotence sur deux exécutions successives.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from scripts import sync_daily

_CSV_HEADER = (
    "tourney_id,tourney_name,surface,draw_size,tourney_level,tourney_date,match_num,"
    "winner_id,winner_name,winner_hand,winner_ioc,winner_ht,"
    "loser_id,loser_name,loser_hand,loser_ioc,loser_ht,"
    "score,best_of,round,w_ace,w_df,l_ace,l_df,winner_rank,loser_rank\n"
)
_CSV_ROW = (
    "2024-580,Australian Open,Hard,128,G,20240114,1,"
    "100001,Carlos Alcaraz,R,ESP,183,"
    "100004,Daniil Medvedev,R,RUS,198,"
    "6-4 7-0 6-0,5,R32,8,1,9,0,36,13\n"
)
FAKE_CSV_CONTENT = (_CSV_HEADER + _CSV_ROW).encode("utf-8")


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


def _fresh_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _fake_get_only_atp_tour_available(url, timeout=None, follow_redirects=None):
    if url.endswith("atp_matches_2024.csv"):
        return FakeResponse(200, FAKE_CSV_CONTENT)
    return FakeResponse(404)


def test_run_degrades_gracefully_when_some_files_are_unavailable(monkeypatch):
    monkeypatch.setattr(sync_daily.httpx, "get", _fake_get_only_atp_tour_available)
    db = _fresh_session()

    report = sync_daily.run(season=2024, db=db)

    statuses = {f["file"]: f["status"] for f in report["files"]}
    assert statuses["atp_matches_2024.csv"] == "ok"
    assert statuses["atp_matches_qual_chall_2024.csv"] == "unavailable"
    assert statuses["atp_matches_futures_2024.csv"] == "unavailable"
    assert statuses["wta_matches_2024.csv"] == "unavailable"
    assert statuses["wta_matches_qual_itf_2024.csv"] == "unavailable"
    assert report["matches_inserted"] == 1
    assert report["players_updated_elo"] >= 2  # Alcaraz + Medvedev
    assert report["confidence_changed"] >= 2
    db.close()


def test_run_is_idempotent_across_two_calls(monkeypatch):
    monkeypatch.setattr(sync_daily.httpx, "get", _fake_get_only_atp_tour_available)
    db = _fresh_session()

    first = sync_daily.run(season=2024, db=db)
    second = sync_daily.run(season=2024, db=db)

    assert first["matches_inserted"] == 1
    assert second["matches_inserted"] == 0  # déjà en base, pas de doublon
    assert db.query(models.Match).count() == 1
    db.close()


def test_run_survives_total_network_outage(monkeypatch):
    monkeypatch.setattr(sync_daily.httpx, "get", lambda *a, **k: FakeResponse(404))
    db = _fresh_session()

    report = sync_daily.run(season=2024, db=db)

    assert report["matches_inserted"] == 0
    assert all(f["status"] == "unavailable" for f in report["files"])
    db.close()
