"""
Teste l'ajustement "format et niveau du tournoi" (services/prediction.py ::
_tournament_context_and_adjustment) : Bo5 en Grand Chelem messieurs (creuse
l'écart de probabilité), tournois ATP/WTA Tour standard hors Masters/Slam/
Finals (resserre par prudence), et absence de nom de tournoi (pas d'ajustement,
comme pour la météo/le H2H quand la donnée manque).

Vraie base SQLite en mémoire (pas de mock sur les requêtes SQLAlchemy).
"""
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import prediction

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def make_db():
    return TestingSessionLocal()


def make_players(db, tour="atp"):
    p1 = models.Player(name="Novak Djokovic", country="SRB", tour=tour, elo_overall=2200)
    p2 = models.Player(name="Daniil Medvedev", country="RUS", tour=tour, elo_overall=2100)
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    return p1, p2


def test_no_tournament_name_omits_context():
    db = make_db()
    p1, p2 = make_players(db)
    result = prediction.build_prediction(db, p1, p2)
    assert "tournament_context" not in result["detail"]
    assert "tournament_adjustment" not in result["detail"]
    db.close()


def test_grand_slam_atp_is_bo5_and_sharpens_probability():
    db = make_db()
    p1, p2 = make_players(db, tour="atp")
    result = prediction.build_prediction(db, p1, p2, tournament_name="US Open")
    ctx = result["detail"]["tournament_context"]
    assert ctx["tier"] == "Grand Chelem"
    assert ctx["format"] == "Bo5 (5 sets gagnants)"
    adj = result["detail"]["tournament_adjustment"]
    # p1 est favori Elo : le format 5 sets doit creuser (augmenter) sa probabilité.
    assert result["win_probability"] > adj["probability_before_tournament"]
    db.close()


def test_grand_slam_wta_is_bo3_and_top_tier_no_dampen():
    db = make_db()
    p1, p2 = make_players(db, tour="wta")
    result = prediction.build_prediction(db, p1, p2, tournament_name="Wimbledon")
    ctx = result["detail"]["tournament_context"]
    assert ctx["tier"] == "Grand Chelem"
    assert ctx["format"] == "Bo3 (3 sets gagnants)"  # pas de Bo5 côté femmes
    # Grand Chelem = tier "top", donc pas d'ajustement de resserrement non plus.
    assert "tournament_adjustment" not in result["detail"]
    db.close()


def test_masters_1000_is_top_tier_no_adjustment():
    db = make_db()
    p1, p2 = make_players(db)
    result = prediction.build_prediction(db, p1, p2, tournament_name="Indian Wells")
    ctx = result["detail"]["tournament_context"]
    assert ctx["tier"] == "Masters 1000 / WTA 1000 / Finals"
    assert "tournament_adjustment" not in result["detail"]
    db.close()


def test_regular_tour_event_dampens_probability():
    db = make_db()
    p1, p2 = make_players(db)
    result = prediction.build_prediction(db, p1, p2, tournament_name="Marseille Open 13")
    ctx = result["detail"]["tournament_context"]
    assert ctx["tier"] == "ATP/WTA Tour"
    adj = result["detail"]["tournament_adjustment"]
    # p1 est favori Elo : le resserrement doit RÉDUIRE sa probabilité (vers 50/50).
    assert result["win_probability"] < adj["probability_before_tournament"]
    db.close()


def test_tournament_name_matching_is_case_insensitive():
    db = make_db()
    p1, p2 = make_players(db)
    result = prediction.build_prediction(db, p1, p2, tournament_name="roland garros")
    assert result["detail"]["tournament_context"]["tier"] == "Grand Chelem"
    db.close()
