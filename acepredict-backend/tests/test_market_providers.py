"""
Tests de services/market_providers.py :: l'interface MarketProvider et son
unique implémentation actuelle (PolymarketProvider). Vérifie surtout que le
passage par cette interface (au lieu d'appeler polymarket_service
directement depuis prediction.py) ne casse pas le mock déjà utilisé par
test_market_prediction.py -- patch.object(polymarket_service,
"get_market_probability", ...) doit toujours être intercepté.
"""
from unittest.mock import patch

from app.services import market_providers, polymarket_service


def test_get_market_provider_returns_polymarket_provider():
    assert isinstance(market_providers.get_market_provider(), market_providers.PolymarketProvider)


def test_is_configured_reflects_polymarket_settings(monkeypatch):
    monkeypatch.setattr(polymarket_service.settings, "polymarket_enabled", False)
    assert market_providers.PolymarketProvider().is_configured() is False
    monkeypatch.setattr(polymarket_service.settings, "polymarket_enabled", True)
    assert market_providers.PolymarketProvider().is_configured() is True


def test_get_probability_delegates_to_polymarket_service():
    fake_result = {"player1_prob": 0.6, "player2_prob": 0.4, "question": "Test"}
    with patch.object(polymarket_service, "get_market_probability", return_value=fake_result) as mocked:
        result = market_providers.PolymarketProvider().get_probability("Carlos Alcaraz", "Novak Djokovic")
    mocked.assert_called_once_with("Carlos Alcaraz", "Novak Djokovic")
    assert result == fake_result


def test_get_probability_returns_none_when_no_market_found():
    with patch.object(polymarket_service, "get_market_probability", return_value=None):
        assert market_providers.PolymarketProvider().get_probability("A", "B") is None
