"""Tests unitaires du moteur Elo — aucune base de données requise."""
from app.services.elo import EloEngine, expected_score, update_elo


def test_expected_score_symmetric():
    assert abs(expected_score(1500, 1500) - 0.5) < 1e-9
    p = expected_score(1600, 1400)
    assert 0.5 < p < 1.0


def test_update_elo_winner_gains_loser_loses():
    new_w, new_l = update_elo(1500, 1500)
    assert new_w > 1500
    assert new_l < 1500
    # conservation approx (somme quasi constante avec un K identique)
    assert abs((new_w - 1500) - (1500 - new_l)) < 1e-6


def test_favorite_gains_less_than_underdog_upset():
    # Le favori (elo plus haut) gagne : petit gain.
    fav_win, _ = update_elo(1700, 1300)
    fav_gain = fav_win - 1700
    # L'outsider (elo plus bas) gagne contre le favori : gros gain.
    underdog_win, _ = update_elo(1300, 1700)
    underdog_gain = underdog_win - 1300
    assert underdog_gain > fav_gain


def test_engine_process_matches_and_predict():
    engine = EloEngine()
    matches = [
        {"winner_key": "alcaraz", "loser_key": "sinner", "surface": "clay"},
        {"winner_key": "alcaraz", "loser_key": "djokovic", "surface": "hard"},
        {"winner_key": "sinner", "loser_key": "djokovic", "surface": "hard"},
    ]
    engine.process_matches(matches)

    assert engine.ratings["alcaraz"].overall > 1500
    assert engine.ratings["djokovic"].overall < 1500

    prediction = engine.predict("alcaraz", "djokovic", surface="hard")
    assert prediction["predicted_winner"] == "alcaraz"
    assert 0.5 < prediction["win_probability"] <= 1.0
