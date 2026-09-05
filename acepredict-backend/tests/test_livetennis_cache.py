"""
Tests du cache agressif de services/livetennis_client.py (quota gratuit
livetennisapi.com : ~30 req/min / ~100 req/jour). Vérifie qu'un deuxième
appel avec les mêmes paramètres, dans la fenêtre TTL, ne redéclenche PAS
d'appel réseau -- httpx.AsyncClient est remplacé par un faux client qui
compte ses appels, comme test_livetennis_upcoming.py.
"""
import asyncio

import httpx
import pytest

from app.services import livetennis_client


@pytest.fixture(autouse=True)
def _reset_caches():
    livetennis_client._reset_all_caches()
    yield
    livetennis_client._reset_all_caches()


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


def make_counting_client(players_by_name, matches, city_by_tournament):
    calls = {"n": 0}

    class FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None, headers=None):
            calls["n"] += 1
            if url.endswith("/players") and "tour" not in (params or {}):
                search = (params or {}).get("search", "")
                match = players_by_name.get(search)
                return FakeResponse([match] if match else [])
            if url.endswith("/players"):
                return FakeResponse(list(players_by_name.values()))
            if url.endswith("/matches"):
                return FakeResponse(matches)
            if "/tournaments/" in url:
                tid = url.rsplit("/", 1)[-1]
                return FakeResponse({"city": city_by_tournament.get(tid)})
            raise AssertionError(f"URL inattendue : {url}")

    return FakeAsyncClient, calls


def test_get_upcoming_list_is_cached_across_calls(monkeypatch):
    FakeAsyncClient, calls = make_counting_client(
        players_by_name={},
        matches=[{
            "tournament": "ATP Finals", "tournament_id": "t1", "tour": "atp",
            "surface": "Hard", "indoor": True, "round": "SF", "is_doubles": False,
            "scheduled_time": "2026-11-16T18:00:00Z",
            "players": {"p1": {"id": 1, "name": "A"}, "p2": {"id": 2, "name": "B"}},
        }],
        city_by_tournament={},
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    r1 = asyncio.run(client.get_upcoming_list(tour="atp"))
    r2 = asyncio.run(client.get_upcoming_list(tour="atp"))

    assert r1 == r2
    assert calls["n"] == 1  # 1 seul appel réseau pour les deux invocations


def test_get_upcoming_list_different_params_bypass_cache(monkeypatch):
    FakeAsyncClient, calls = make_counting_client(
        players_by_name={},
        matches=[],
        city_by_tournament={},
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    asyncio.run(client.get_upcoming_list(tour="atp"))
    asyncio.run(client.get_upcoming_list(tour="wta"))  # clé de cache différente

    assert calls["n"] == 2


def test_find_player_id_is_cached_across_instances(monkeypatch):
    """Chaque requête HTTP recrée un LiveTennisApiClient (cf.
    get_live_client()) -- le cache doit donc survivre au-delà d'une seule
    instance, comme en production."""
    FakeAsyncClient, calls = make_counting_client(
        players_by_name={"Carlos Alcaraz": {"id": 1, "name": "Carlos Alcaraz"}},
        matches=[],
        city_by_tournament={},
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    async def lookup_via_new_instance():
        client = livetennis_client.LiveTennisApiClient()
        async with httpx.AsyncClient() as http_client:
            return await client._find_player_id(http_client, "Carlos Alcaraz")

    id1 = asyncio.run(lookup_via_new_instance())
    id2 = asyncio.run(lookup_via_new_instance())

    assert id1 == id2 == 1
    assert calls["n"] == 1


def test_get_upcoming_between_is_cached_and_order_independent(monkeypatch):
    FakeAsyncClient, calls = make_counting_client(
        players_by_name={
            "Carlos Alcaraz": {"id": 1, "name": "Carlos Alcaraz"},
            "Jannik Sinner": {"id": 2, "name": "Jannik Sinner"},
        },
        matches=[{
            "tournament": "ATP Finals", "tournament_id": "t1",
            "surface": "Hard", "indoor": True, "round": "SF",
            "scheduled_time": "2026-11-16T18:00:00Z",
            "players": {"p1": {"id": 1}, "p2": {"id": 2}},
        }],
        city_by_tournament={"t1": "Turin"},
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    r1 = asyncio.run(client.get_upcoming_between("Carlos Alcaraz", "Jannik Sinner"))
    calls_after_first = calls["n"]
    # Même paire, ordre inversé : doit toujours taper le cache (clé triée).
    r2 = asyncio.run(client.get_upcoming_between("Jannik Sinner", "Carlos Alcaraz"))

    assert r1 == r2
    assert calls["n"] == calls_after_first  # aucun appel réseau supplémentaire


def test_get_player_profile_returns_raw_object_and_is_cached(monkeypatch):
    FakeAsyncClient, calls = make_counting_client(
        players_by_name={"Carlos Alcaraz": {"id": 1, "name": "Carlos Alcaraz", "ranking": 2, "country": "ESP"}},
        matches=[],
        city_by_tournament={},
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    p1 = asyncio.run(client.get_player_profile("Carlos Alcaraz"))
    p2 = asyncio.run(client.get_player_profile("Carlos Alcaraz"))

    assert p1 == {"id": 1, "name": "Carlos Alcaraz", "ranking": 2, "country": "ESP"}
    assert p1 == p2
    assert calls["n"] == 1


def test_get_player_profile_returns_none_when_not_found(monkeypatch):
    FakeAsyncClient, calls = make_counting_client(players_by_name={}, matches=[], city_by_tournament={})
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    assert asyncio.run(client.get_player_profile("Joueur Inconnu")) is None


def test_get_tournament_city_public_wrapper_is_cached(monkeypatch):
    FakeAsyncClient, calls = make_counting_client(
        players_by_name={}, matches=[], city_by_tournament={"t1": "Turin"},
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    c1 = asyncio.run(client.get_tournament_city("t1"))
    c2 = asyncio.run(client.get_tournament_city("t1"))

    assert c1 == c2 == "Turin"
    assert calls["n"] == 1
