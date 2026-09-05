"""
Tests unitaires de services/polymarket_service.py.

Deux couches testées séparément :
  - _fetch_tennis_markets : l'appel réseau (mocké) vers la Gamma API et son
    cache mémoire, dégradation gracieuse sur erreur réseau/JSON.
  - get_market_probability / _match_moneyline_market : le matching
    "safety-first" nom de joueur <-> marché, sur une liste de marchés déjà
    récupérée (on patch directement _fetch_tennis_markets pour ces tests-là,
    pas besoin de repasser par le mock réseau).

Jamais de vrai appel réseau dans les tests.
"""
import json
from unittest.mock import patch

from app.services import polymarket_service


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


def _market(**overrides):
    market = {
        "question": "Carlos Alcaraz vs Novak Djokovic - Who will win?",
        "outcomes": json.dumps(["Carlos Alcaraz", "Novak Djokovic"]),
        "outcomePrices": json.dumps(["0.62", "0.38"]),
        "closed": False,
        "active": True,
    }
    market.update(overrides)
    return market


def _reset_cache():
    polymarket_service._tennis_markets_cache = None


# ------------------------------------------------- _fetch_tennis_markets ---

def test_fetch_tennis_markets_not_configured_still_returns_list(monkeypatch):
    # is_configured() n'est vérifié que dans get_market_probability, pas ici
    # -- _fetch_tennis_markets reste une fonction réseau pure, testée à part.
    _reset_cache()
    monkeypatch.setattr(
        polymarket_service.httpx, "get",
        lambda *a, **k: FakeResponse(200, {"events": [{"markets": [_market()]}]}),
    )
    markets = polymarket_service._fetch_tennis_markets()
    assert len(markets) == 1


def test_fetch_tennis_markets_handles_bare_list_response(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        polymarket_service.httpx, "get",
        lambda *a, **k: FakeResponse(200, [{"markets": [_market(), _market()]}]),
    )
    assert len(polymarket_service._fetch_tennis_markets()) == 2


def test_fetch_tennis_markets_network_error_returns_empty_list(monkeypatch):
    _reset_cache()

    def fake_get(*a, **k):
        raise ConnectionError("boom")

    monkeypatch.setattr(polymarket_service.httpx, "get", fake_get)
    assert polymarket_service._fetch_tennis_markets() == []


def test_fetch_tennis_markets_bad_status_returns_empty_list(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(polymarket_service.httpx, "get", lambda *a, **k: FakeResponse(500))
    assert polymarket_service._fetch_tennis_markets() == []


def test_fetch_tennis_markets_uses_cache_within_ttl(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return FakeResponse(200, {"events": [{"markets": [_market()]}]})

    monkeypatch.setattr(polymarket_service.httpx, "get", fake_get)
    polymarket_service._fetch_tennis_markets()
    polymarket_service._fetch_tennis_markets()
    assert calls["n"] == 1  # 2e appel servi depuis le cache, pas de 2e requête réseau
    _reset_cache()


# ------------------------------------------------- get_market_probability --

def test_not_configured_returns_none(monkeypatch):
    monkeypatch.setattr(polymarket_service.settings, "polymarket_enabled", False)
    assert polymarket_service.get_market_probability("Carlos Alcaraz", "Novak Djokovic") is None


def test_missing_player_names_returns_none(monkeypatch):
    monkeypatch.setattr(polymarket_service.settings, "polymarket_enabled", True)
    assert polymarket_service.get_market_probability("", "Novak Djokovic") is None


def test_valid_two_outcome_market_matches_and_normalizes():
    result = _run_match(markets=[_market()])
    assert result is not None
    assert result["question"].startswith("Carlos Alcaraz")
    assert result["player1_prob"] == 0.62
    assert result["player2_prob"] == 0.38


def test_no_markets_returns_none():
    assert _run_match(markets=[]) is None


def test_closed_market_is_skipped():
    assert _run_match(markets=[_market(closed=True)]) is None


def test_inactive_market_is_skipped():
    assert _run_match(markets=[_market(active=False)]) is None


def test_market_with_wrong_player_not_mentioned_is_skipped():
    result = _run_match(markets=[_market(
        outcomes=json.dumps(["Carlos Alcaraz", "Jannik Sinner"]),
        question="Carlos Alcaraz vs Jannik Sinner - Who will win?",
    )])
    assert result is None


def test_market_with_three_outcomes_is_skipped():
    result = _run_match(markets=[_market(
        outcomes=json.dumps(["Carlos Alcaraz", "Novak Djokovic", "Draw"]),
        outcomePrices=json.dumps(["0.5", "0.3", "0.2"]),
    )])
    assert result is None


def test_ambiguous_multiple_candidate_markets_returns_none():
    # Deux marchés distincts matchent tous les deux les deux joueurs (ex: le
    # match complet ET le 1er set) -> on ne devine pas, on renvoie None.
    assert _run_match(markets=[_market(), _market()]) is None


def test_unrelated_markets_are_ignored():
    unrelated = _market(
        question="Jannik Sinner vs Alexander Zverev - Who will win?",
        outcomes=json.dumps(["Jannik Sinner", "Alexander Zverev"]),
    )
    result = _run_match(markets=[unrelated, _market()])
    assert result is not None
    assert result["question"].startswith("Carlos Alcaraz")


def _run_match(markets):
    """Helper : patch _fetch_tennis_markets (pas httpx directement -- ces
    tests portent sur le matching, pas sur la récupération réseau) et
    appelle get_market_probability pour Alcaraz vs Djokovic."""
    with patch.object(polymarket_service.settings, "polymarket_enabled", True), \
         patch.object(polymarket_service, "_fetch_tennis_markets", return_value=markets):
        return polymarket_service.get_market_probability("Carlos Alcaraz", "Novak Djokovic")
