"""
Tests unitaires de l'ajustement météo appliqué à la prédiction — aucune base
de données requise. Depuis le refactor "synchronisation automatique" (cf.
README "Synchronisation des données"), build_prediction() ne va plus
chercher la météo elle-même : le dict `weather` est fourni tel quel par
l'appelant (routers/analyses.py, à partir de la Fixture synchronisée par
scripts/sync_hourly.py) — ces tests passent donc directement le paramètre
`weather=` plutôt que de mocker weather_service, qui n'est plus appelé du
tout par prediction.py (cf. tests/test_analyses_weather_market.py pour la
reconstruction du dict `weather` depuis une Fixture, et l'ancien test
"carpet -> indoor" qui vivait ici : cette décision est prise par l'appelant
maintenant, plus par build_prediction).
"""
from app.services import prediction


class FakePlayer:
    def __init__(self, id, elo_overall=1500.0, elo_hard=1500.0, elo_clay=1500.0, elo_grass=1500.0):
        self.id = id
        self.name = id  # champ obligatoire côté vrai modèle Player, utilisé par prediction.py
        self.elo_overall = elo_overall
        self.elo_hard = elo_hard
        self.elo_clay = elo_clay
        self.elo_grass = elo_grass


def test_no_weather_provided_no_weather_in_detail():
    p1, p2 = FakePlayer("p1", 1600), FakePlayer("p2", 1500)
    result = prediction.build_prediction(None, p1, p2)
    assert "weather" not in result["detail"]


def test_weather_none_returns_none_even_with_city():
    # match_city ne déclenche plus rien par lui-même (cf. docstring de
    # build_prediction) : sans `weather=` fourni, rien n'apparaît.
    p1, p2 = FakePlayer("p1", 1600), FakePlayer("p2", 1500)
    result = prediction.build_prediction(None, p1, p2, match_city="Paris")
    assert "weather" not in result["detail"]


def test_strong_wind_dampens_probability_towards_half():
    p1, p2 = FakePlayer("p1", 1700), FakePlayer("p2", 1400)
    baseline = prediction.build_prediction(None, p1, p2)
    baseline_prob = baseline["win_probability"]

    windy = prediction.build_prediction(
        None, p1, p2, match_city="Paris",
        weather={"indoor": False, "temp_c": 22, "wind_kmh": 35, "humidity_pct": 50, "description": "vent fort"},
    )

    assert windy["detail"]["weather"]["wind_kmh"] == 35
    assert windy["detail"]["weather_adjustment"] is not None
    # La probabilité ajustée doit être plus proche de 0.5 que la probabilité de base.
    assert abs(windy["win_probability"] - 0.5) < abs(baseline_prob - 0.5)
    # Le gagnant prédit ne doit pas changer sous l'effet du vent seul (dampening, pas un biais dirigé).
    assert windy["predicted_winner_id"] == baseline["predicted_winner_id"]


def test_calm_weather_no_adjustment():
    p1, p2 = FakePlayer("p1", 1700), FakePlayer("p2", 1400)
    result = prediction.build_prediction(
        None, p1, p2, match_city="Paris",
        weather={"indoor": False, "temp_c": 20, "wind_kmh": 5, "humidity_pct": 40, "description": "calme"},
    )
    assert "weather_adjustment" not in result["detail"]


def test_indoor_match_skips_adjustment_even_with_city():
    p1, p2 = FakePlayer("p1", 1700), FakePlayer("p2", 1400)
    result = prediction.build_prediction(
        None, p1, p2, surface="hard", match_city="Paris", weather={"indoor": True},
    )
    assert result["detail"]["weather"] == {"indoor": True}
    assert "weather_adjustment" not in result["detail"]
