"""Tests de services/data_confidence.py."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.models import DataConfidenceEnum
from app.services import data_confidence


def _fresh_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_no_matches_no_bio_is_insufficient():
    assert data_confidence.compute_confidence(0, has_bio_data=False) == DataConfidenceEnum.insufficient


def test_no_matches_with_bio_is_low():
    assert data_confidence.compute_confidence(0, has_bio_data=True) == DataConfidenceEnum.low


def test_few_matches_is_medium():
    assert data_confidence.compute_confidence(1) == DataConfidenceEnum.medium
    assert data_confidence.compute_confidence(data_confidence.HIGH_MATCH_THRESHOLD - 1) == DataConfidenceEnum.medium


def test_many_matches_is_high():
    assert data_confidence.compute_confidence(data_confidence.HIGH_MATCH_THRESHOLD) == DataConfidenceEnum.high
    assert data_confidence.compute_confidence(200) == DataConfidenceEnum.high


def test_bio_data_ignored_once_matches_exist():
    # has_bio_data ne sert qu'à distinguer insufficient/low quand il n'y a
    # aucun match -- au-delà, seul le nombre de matchs compte.
    assert data_confidence.compute_confidence(1, has_bio_data=False) == DataConfidenceEnum.medium
    assert data_confidence.compute_confidence(1, has_bio_data=True) == DataConfidenceEnum.medium


def test_label_and_description_cover_every_enum_value():
    for value in DataConfidenceEnum:
        assert data_confidence.label(value)
        assert data_confidence.description(value)


def test_has_bio_signal_true_when_any_field_present():
    class FakePlayer:
        current_rank = None
        country = "FRA"
        hand = None
        height_cm = None

    assert data_confidence.has_bio_signal(FakePlayer()) is True


def test_has_bio_signal_false_when_nothing_known():
    class FakePlayer:
        current_rank = None
        country = None
        hand = None
        height_cm = None

    assert data_confidence.has_bio_signal(FakePlayer()) is False


def test_recompute_all_sets_confidence_from_match_counts():
    db = _fresh_session()
    veteran = models.Player(name="Veteran", tour="atp")
    rookie = models.Player(name="Rookie", tour="atp")
    ghost = models.Player(name="Ghost", tour="atp")  # aucun match, aucune donnée bio
    scouted = models.Player(name="Scouted", tour="atp", country="FRA")  # aucun match, bio connue
    db.add_all([veteran, rookie, ghost, scouted])
    db.commit()
    for p in (veteran, rookie, ghost, scouted):
        db.refresh(p)

    # veteran : 16 matchs (alternant victoires/défaites face à rookie) -> high
    for i in range(16):
        winner, loser = (veteran, rookie) if i % 2 == 0 else (rookie, veteran)
        db.add(models.Match(player1_id=winner.id, player2_id=loser.id, winner_id=winner.id, source="manual"))
    db.commit()

    changed = data_confidence.recompute_all(db)
    # veteran/rookie/scouted changent de niveau ; ghost reste "insufficient"
    # (sa valeur par défaut) puisque rien n'a changé pour lui.
    assert changed == 3

    db.refresh(veteran)
    db.refresh(rookie)
    db.refresh(ghost)
    db.refresh(scouted)

    assert veteran.data_confidence == DataConfidenceEnum.high  # 16 matchs en tant que gagnant/perdant
    assert rookie.data_confidence == DataConfidenceEnum.high   # même nombre de matchs, juste résultats inversés
    assert ghost.data_confidence == DataConfidenceEnum.insufficient
    assert scouted.data_confidence == DataConfidenceEnum.low

    # Un 2e passage sans changement de données ne rapporte aucun changement.
    assert data_confidence.recompute_all(db) == 0
    db.close()
