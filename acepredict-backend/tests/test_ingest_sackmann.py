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
