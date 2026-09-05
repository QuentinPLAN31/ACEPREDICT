"""
Tests unitaires de services/weather_providers.py : les deux fournisseurs
météo interchangeables (OpenWeatherMap, Open-Meteo) et leur cache. Aucun
vrai appel réseau -- httpx.get est mocké, comme test_polymarket_service.py
le fait pour Polymarket.
"""
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.services import weather_providers


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_provider_caches():
    weather_providers.OpenWeatherMapProvider._cache.clear()
    weather_providers.OpenMeteoProvider._geocode_cache.clear()
    weather_providers.OpenMeteoProvider._forecast_cache.clear()
    yield
    weather_providers.OpenWeatherMapProvider._cache.clear()
    weather_providers.OpenMeteoProvider._geocode_cache.clear()
    weather_providers.OpenMeteoProvider._forecast_cache.clear()


# ------------------------------------------------------- OpenWeatherMap ----

def test_openweathermap_not_configured_without_key(monkeypatch):
    monkeypatch.setattr(settings, "weather_api_key", "")
    provider = weather_providers.OpenWeatherMapProvider()
    assert provider.is_configured() is False
    assert provider.get_conditions("Paris", None) is None


def test_openweathermap_current_conditions(monkeypatch):
    monkeypatch.setattr(settings, "weather_api_key", "fake-key")
    monkeypatch.setattr(
        weather_providers.httpx, "get",
        lambda url, params=None, timeout=None: FakeResponse(200, {
            "main": {"temp": 24.3, "humidity": 55},
            "wind": {"speed": 5.0},  # m/s -> 18 km/h
            "weather": [{"description": "ciel dégagé"}],
        }),
    )
    provider = weather_providers.OpenWeatherMapProvider()
    result = provider.get_conditions("Paris", None)
    assert result["temp_c"] == 24.3
    assert result["wind_kmh"] == 18.0
    assert result["humidity_pct"] == 55
    assert result["description"] == "ciel dégagé"


def test_openweathermap_uses_cache_within_ttl(monkeypatch):
    monkeypatch.setattr(settings, "weather_api_key", "fake-key")
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return FakeResponse(200, {
            "main": {"temp": 20.0, "humidity": 40},
            "wind": {"speed": 2.0},
            "weather": [{"description": "calme"}],
        })

    monkeypatch.setattr(weather_providers.httpx, "get", fake_get)
    provider = weather_providers.OpenWeatherMapProvider()
    provider.get_conditions("Paris", None)
    provider.get_conditions("Paris", None)
    assert calls["n"] == 1  # 2e appel servi depuis le cache


def test_openweathermap_bad_status_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "weather_api_key", "fake-key")
    monkeypatch.setattr(weather_providers.httpx, "get", lambda *a, **k: FakeResponse(500))
    provider = weather_providers.OpenWeatherMapProvider()
    assert provider.get_conditions("Paris", None) is None


def test_openweathermap_network_error_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "weather_api_key", "fake-key")

    def raise_err(*a, **k):
        raise ConnectionError("boom")

    monkeypatch.setattr(weather_providers.httpx, "get", raise_err)
    provider = weather_providers.OpenWeatherMapProvider()
    assert provider.get_conditions("Paris", None) is None


# ------------------------------------------------------------ Open-Meteo ---

def test_openmeteo_always_configured():
    assert weather_providers.OpenMeteoProvider().is_configured() is True


def test_openmeteo_current_conditions(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return FakeResponse(200, {"results": [{"latitude": 48.85, "longitude": 2.35}]})
        return FakeResponse(200, {
            "current": {
                "temperature_2m": 19.5, "wind_speed_10m": 12.0,
                "relative_humidity_2m": 60, "weather_code": 1,
            },
        })

    monkeypatch.setattr(weather_providers.httpx, "get", fake_get)
    provider = weather_providers.OpenMeteoProvider()
    result = provider.get_conditions("Paris", None)
    assert result["temp_c"] == 19.5
    assert result["wind_kmh"] == 12.0
    assert result["humidity_pct"] == 60
    assert result["description"] == "plutôt dégagé"


def test_openmeteo_forecast_picks_nearest_hour(monkeypatch):
    match_date = datetime.utcnow() + timedelta(days=2)
    target_iso = match_date.replace(minute=0, second=0, microsecond=0).isoformat()

    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return FakeResponse(200, {"results": [{"latitude": 48.85, "longitude": 2.35}]})
        return FakeResponse(200, {
            "hourly": {
                "time": [target_iso],
                "temperature_2m": [30.0],
                "wind_speed_10m": [40.0],
                "relative_humidity_2m": [20],
                "weather_code": [95],
            },
        })

    monkeypatch.setattr(weather_providers.httpx, "get", fake_get)
    provider = weather_providers.OpenMeteoProvider()
    result = provider.get_conditions("Paris", match_date)
    assert result["temp_c"] == 30.0
    assert result["wind_kmh"] == 40.0
    assert result["description"] == "orage"


def test_openmeteo_geocoding_failure_returns_none(monkeypatch):
    monkeypatch.setattr(weather_providers.httpx, "get", lambda *a, **k: FakeResponse(200, {"results": []}))
    provider = weather_providers.OpenMeteoProvider()
    assert provider.get_conditions("VilleInconnueXYZ", None) is None


def test_openmeteo_no_city_returns_none():
    provider = weather_providers.OpenMeteoProvider()
    assert provider.get_conditions("", None) is None


def test_openmeteo_caches_geocoding_separately_from_forecast(monkeypatch):
    calls = {"geocode": 0, "forecast": 0}

    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            calls["geocode"] += 1
            return FakeResponse(200, {"results": [{"latitude": 48.85, "longitude": 2.35}]})
        calls["forecast"] += 1
        return FakeResponse(200, {
            "current": {"temperature_2m": 18.0, "wind_speed_10m": 3.0, "relative_humidity_2m": 50, "weather_code": 0},
        })

    monkeypatch.setattr(weather_providers.httpx, "get", fake_get)
    provider = weather_providers.OpenMeteoProvider()
    provider.get_conditions("Paris", None)
    provider.get_conditions("Paris", None)
    assert calls["geocode"] == 1
    assert calls["forecast"] == 1


# --------------------------------------------------- get_weather_provider --

def test_get_weather_provider_defaults_to_openweathermap():
    assert isinstance(weather_providers.get_weather_provider(), weather_providers.OpenWeatherMapProvider)


def test_get_weather_provider_selects_open_meteo_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "weather_provider", "open-meteo")
    assert isinstance(weather_providers.get_weather_provider(), weather_providers.OpenMeteoProvider)
    monkeypatch.setattr(settings, "weather_provider", "openweathermap")
