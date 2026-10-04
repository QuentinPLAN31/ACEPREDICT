"""
Tests de scripts/ingest_sackmann.py :: ingest_csv — surtout l'idempotence
(nécessaire pour scripts/sync_daily.py, qui ré-ingère chaque jour le CSV de
la saison en cours). SQLite en mémoire, comme les autres tests DB du projet.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from scripts.ingest_sackmann import ingest_csv

SAMPLE_CSV = "data/sample/atp_matches_sample.csv"


def _fresh_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_ingest_creates_matches_and_players():
    db = _fresh_session()
    n = ingest_csv(SAMPLE_CSV, tour="atp", db=db)
    assert n > 0
    assert db.query(models.Match).count() == n
    assert db.query(models.Player).count() > 0
    db.close()


def test_reingesting_same_file_is_idempotent():
    db = _fresh_session()
    first = ingest_csv(SAMPLE_CSV, tour="atp", db=db)
    matches_after_first = db.query(models.Match).count()

    second = ingest_csv(SAMPLE_CSV, tour="atp", db=db)

    assert second == 0  # aucun match nouvellement inséré la 2e fois
    assert db.query(models.Match).count() == matches_after_first  # pas de doublons
    assert first > 0
    db.close()


def test_reingesting_does_not_duplicate_players_or_competitions():
    db = _fresh_session()
    ingest_csv(SAMPLE_CSV, tour="atp", db=db)
    players_after_first = db.query(models.Player).count()
    competitions_after_first = db.query(models.Competition).count()

    ingest_csv(SAMPLE_CSV, tour="atp", db=db)

    assert db.query(models.Player).count() == players_after_first
    assert db.query(models.Competition).count() == competitions_after_first
    db.close()


def test_reingest_backfills_serve_detail_on_old_matches(tmp_path):
    """Les matchs importés avant l'ajout du détail de service (aces/DF seulement)
    sont complétés au ré-import, sans doublon."""
    header = ("tourney_id,tourney_name,surface,draw_size,tourney_level,tourney_date,match_num,"
              "winner_id,winner_name,winner_hand,winner_ioc,winner_ht,loser_id,loser_name,loser_hand,"
              "loser_ioc,loser_ht,score,best_of,round,w_ace,w_df,w_svpt,w_1stIn,w_1stWon,w_2ndWon,"
              "w_SvGms,w_bpSaved,w_bpFaced,l_ace,l_df,l_svpt,l_1stIn,l_1stWon,l_2ndWon,l_SvGms,"
              "l_bpSaved,l_bpFaced,winner_rank,loser_rank\n")
    row = ("2026-1,Test Open,Hard,32,A,20260105,1,W1,Joueur Un,R,FRA,185,L1,Joueur Deux,R,ESP,180,"
           "6-4 6-4,3,R32,5,1,60,40,30,12,10,2,3,3,2,58,35,22,12,9,4,7,10,20\n")
    csv_path = tmp_path / "m.csv"
    csv_path.write_text(header + row, encoding="utf-8")

    db = _fresh_session()
    assert ingest_csv(str(csv_path), tour="atp", db=db) == 1
    m = db.query(models.Match).one()
    m.stats = {"w_ace": "5", "w_df": "1", "l_ace": "3", "l_df": "2"}
    db.commit()
    assert "w_svpt" not in db.get(models.Match, m.id).stats

    assert ingest_csv(str(csv_path), tour="atp", db=db) == 0
    assert db.query(models.Match).count() == 1
    st = db.get(models.Match, m.id).stats
    assert st["w_svpt"] == "60" and st["l_bpFaced"] == "7"
