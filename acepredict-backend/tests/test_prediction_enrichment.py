"""
Tests du moteur de prédiction enrichi : head-to-head, fatigue récente, et
dégradation gracieuse du commentaire IA (services/ai_narrative.py) sans clé
configurée. Utilise une vraie base SQLite en mémoire (pas de mock sur les
requêtes SQLAlchemy) pour que les jointures/filtres soient réellement testés.
"""
from datetime import datetime, timedelta

from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import ai_narrative, prediction

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def make_db():
    return TestingSessionLocal()


def make_players(db):
    p1 = models.Player(name="Novak Djokovic", country="SRB", tour="atp", elo_overall=2200)
    p2 = models.Player(name="Daniil Medvedev", country="RUS", tour="atp", elo_overall=2100)
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    return p1, p2


def add_match(db, p1, p2, winner, days_ago, surface="hard"):
    db.add(models.Match(
        player1_id=p1.id,
        player2_id=p2.id,
        winner_id=winner.id,
        tourney_date=datetime.utcnow() - timedelta(days=days_ago),
        surface=surface,
        source="manual",
    ))
    db.commit()


# ---------------------------------------------------------------- H2H -----

def test_h2h_below_min_sample_no_adjustment():
    db = make_db()
    p1, p2 = make_players(db)
    # Un seul affrontement passé : sous H2H_MIN_SAMPLE, pas d'ajustement.
    add_match(db, p1, p2, winner=p2, days_ago=400)

    result = prediction.build_prediction(db, p1, p2)
    assert result["detail"]["h2h"]["total"] == 1
    assert "h2h_adjustment" not in result["detail"]
    db.close()


def test_h2h_clear_leader_adjusts_probability_when_it_favors_current_winner():
    db = make_db()
    p1, p2 = make_players(db)
    # p1 (déjà favori Elo) mène aussi largement le head-to-head : l'ajustement
    # doit pousser la probabilité VERS le haut (dans le même sens que l'Elo).
    for _ in range(4):
        add_match(db, p1, p2, winner=p1, days_ago=300)
    add_match(db, p1, p2, winner=p2, days_ago=200)

    result = prediction.build_prediction(db, p1, p2)
    h2h = result["detail"]["h2h"]
    assert h2h == {
        "total": 5, "wins_player1": 4, "wins_player2": 1,
        "recent_meetings": h2h["recent_meetings"],
    }
    assert len(h2h["recent_meetings"]) == 5
    adj = result["detail"]["h2h_adjustment"]
    assert adj["probability_before_h2h"] < result["win_probability"]
    # Capé à +/- H2H_MAX_ADJUSTMENT quel que soit l'écart historique.
    assert abs(result["win_probability"] - adj["probability_before_h2h"]) <= prediction.H2H_MAX_ADJUSTMENT + 1e-9
    db.close()


def test_h2h_leader_opposing_elo_pulls_probability_down():
    db = make_db()
    p1, p2 = make_players(db)  # p1 favori Elo (2200 vs 2100)
    # Mais p2 domine largement le head-to-head : l'ajustement doit RÉDUIRE
    # la probabilité du favori Elo (sans jamais l'inverser, cap oblige).
    for _ in range(5):
        add_match(db, p1, p2, winner=p2, days_ago=250)

    result = prediction.build_prediction(db, p1, p2)
    adj = result["detail"]["h2h_adjustment"]
    assert result["win_probability"] < adj["probability_before_h2h"]
    assert result["predicted_winner_id"] == p1.id  # Elo reste dominant, juste atténué
    db.close()


def test_no_h2h_history_omits_h2h_key():
    db = make_db()
    p1, p2 = make_players(db)
    result = prediction.build_prediction(db, p1, p2)
    assert "h2h" not in result["detail"]
    assert "h2h_adjustment" not in result["detail"]
    db.close()


# -------------------------------------------------------------- fatigue ---

def test_fatigue_counts_matches_in_window():
    db = make_db()
    p1, p2 = make_players(db)
    third = models.Player(name="Carlos Alcaraz", country="ESP", tour="atp", elo_overall=2150)
    db.add(third)
    db.commit()
    db.refresh(third)

    # p1 a enchaîné 3 matchs (contre `third`) sur les 14 derniers jours ; p2 aucun.
    for days_ago in (2, 6, 10):
        add_match(db, p1, third, winner=p1, days_ago=days_ago)

    result = prediction.build_prediction(db, p1, p2)
    assert result["detail"]["fatigue_player1"]["matches_last_14_days"] == 3
    assert result["detail"]["fatigue_player1"]["days_since_last_match"] == 2
    assert result["detail"]["fatigue_player2"]["matches_last_14_days"] == 0
    # p1 est déjà favori Elo ET plus chargé : l'ajustement doit resserrer sa probabilité.
    adj = result["detail"]["fatigue_adjustment"]
    assert result["win_probability"] < adj["probability_before_fatigue"]
    db.close()


def test_fatigue_small_gap_no_adjustment():
    db = make_db()
    p1, p2 = make_players(db)
    add_match(db, p1, p2, winner=p1, days_ago=3)  # 1 seul match récent chacun via ce h2h : écart nul
    result = prediction.build_prediction(db, p1, p2)
    assert "fatigue_adjustment" not in result["detail"]
    db.close()


# --------------------------------------------------- commentaire IA -------

def test_ai_narrative_not_configured_returns_none(monkeypatch):
    monkeypatch.setattr(ai_narrative.settings, "anthropic_api_key", "")
    assert ai_narrative.is_configured() is False
    assert ai_narrative.generate_narrative({"win_probability": 0.6}) is None


def test_ai_narrative_api_error_degrades_gracefully(monkeypatch):
    """Clé présente mais l'appel réseau échoue (mauvaise clé, Anthropic down...)
    -> None, jamais d'exception qui remonterait jusqu'à /analyses."""
    monkeypatch.setattr(ai_narrative.settings, "anthropic_api_key", "sk-ant-fake")

    class FakeResponse:
        status_code = 401

        def json(self):
            return {"error": "invalid api key"}

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(ai_narrative.httpx, "post", fake_post)
    assert ai_narrative.generate_narrative({
        "player1_name": "A", "player2_name": "B", "winner_name": "A",
        "elo_player1": 2000, "elo_player2": 1900, "elo_diff": 100,
        "win_probability": 0.6,
    }) is None


def test_build_prediction_includes_ai_narrative_key_even_when_unconfigured():
    db = make_db()
    p1, p2 = make_players(db)
    result = prediction.build_prediction(db, p1, p2)
    assert "ai_narrative" in result["detail"]
    assert result["detail"]["ai_narrative"] is None  # pas de clé dans l'environnement de test
    assert result["model_version"] == prediction.MODEL_VERSION
    db.close()
