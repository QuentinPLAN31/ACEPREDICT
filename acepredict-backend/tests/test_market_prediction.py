"""
Teste l'ajustement "probabilité de marché" (services/prediction.py ::
_apply_market_blend) : fusion pondérée avec Polymarket, seul ajustement
capable de changer le favori prédit quand le marché contredit franchement
le modèle Elo. Depuis le refactor "synchronisation automatique" (cf. README
"Synchronisation des données"), build_prediction() ne va plus chercher le
marché elle-même : le dict `market` est fourni tel quel par l'appelant
(routers/analyses.py, à partir de la Fixture synchronisée par
scripts/sync_hourly.py) — ces tests passent donc directement le paramètre
`market=` plutôt que de mocker polymarket_service, qui n'est plus appelé du
tout par prediction.py (cf. tests/test_market_providers.py pour l'interface
MarketProvider elle-même, inchangée).
"""
from app.services import prediction


class FakePlayer:
    def __init__(self, id, elo_overall=1500.0, elo_hard=1500.0, elo_clay=1500.0, elo_grass=1500.0):
        self.id = id
        self.name = id
        self.elo_overall = elo_overall
        self.elo_hard = elo_hard
        self.elo_clay = elo_clay
        self.elo_grass = elo_grass


def test_no_market_provided_no_adjustment():
    p1, p2 = FakePlayer("p1", 1700), FakePlayer("p2", 1400)
    result = prediction.build_prediction(None, p1, p2)
    assert "market_adjustment" not in result["detail"]


def test_market_confirms_favorite_moves_probability_towards_market():
    p1, p2 = FakePlayer("p1", 1600), FakePlayer("p2", 1500)  # p1 léger favori Elo
    baseline = prediction.build_prediction(None, p1, p2)
    baseline_prob = baseline["win_probability"]

    result = prediction.build_prediction(
        None, p1, p2,
        market={"player1_prob": 0.9, "player2_prob": 0.1, "question": "p1 vs p2 - Who will win?"},
    )

    assert result["predicted_winner_id"] == "p1"
    assert result["detail"]["market_adjustment"]["winner_flipped"] is False
    # Le marché est très favorable à p1 (0.9) : la probabilité fusionnée doit
    # être strictement plus haute que la probabilité Elo seule.
    assert result["win_probability"] > baseline_prob


def test_market_disagrees_flips_predicted_winner():
    # Écart Elo modéré (p1 léger favori, ~64%) : avec MARKET_BLEND_WEIGHT=0.4,
    # un marché quasi certain de l'issue inverse (0.98 pour p2) suffit à faire
    # basculer la fusion sous 50%. Un écart Elo énorme (ex: 300+ points, >83%
    # de probabilité) résiste volontairement au marché seul — cf. commentaire
    # sur MARKET_BLEND_WEIGHT dans prediction.py : le poids est significatif
    # mais ne permet pas à un marché isolé d'écraser un signal structurel fort.
    p1, p2 = FakePlayer("p1", 1600), FakePlayer("p2", 1500)
    baseline = prediction.build_prediction(None, p1, p2)
    assert baseline["predicted_winner_id"] == "p1"

    result = prediction.build_prediction(
        None, p1, p2,
        market={"player1_prob": 0.02, "player2_prob": 0.98, "question": "p1 vs p2 - Who will win?"},
    )

    assert result["predicted_winner_id"] == "p2"
    assert result["detail"]["market_adjustment"]["winner_flipped"] is True
    assert result["win_probability"] >= 0.5


def test_market_adjustment_detail_contains_raw_market_probabilities():
    p1, p2 = FakePlayer("p1", 1600), FakePlayer("p2", 1500)
    result = prediction.build_prediction(
        None, p1, p2,
        market={"player1_prob": 0.7, "player2_prob": 0.3, "question": "Test market"},
    )

    adj = result["detail"]["market_adjustment"]
    assert adj["market_player1_prob"] == 0.7
    assert adj["market_player2_prob"] == 0.3
    assert adj["market_question"] == "Test market"
    assert "probability_before_market" in adj


def test_market_probability_never_exceeds_cap():
    p1, p2 = FakePlayer("p1", 1900), FakePlayer("p2", 1000)  # écart Elo énorme
    result = prediction.build_prediction(
        None, p1, p2,
        market={"player1_prob": 0.99, "player2_prob": 0.01, "question": "Test market"},
    )
    assert result["win_probability"] <= 0.99
