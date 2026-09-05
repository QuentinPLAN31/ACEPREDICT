"""
Tests unitaires de la résolution "prochains matchs entre deux joueurs" —
aucun appel réseau réel : httpx.AsyncClient est remplacé par un faux client
qui rejoue des réponses en dur, comme le service est censé se comporter
face à livetennisapi.com (cf. services/livetennis_client.py).
"""
import asyncio

import httpx
import pytest

from app.services import livetennis_client


@pytest.fixture(autouse=True)
def _reset_livetennis_caches():
    """livetennis_client met désormais en cache (singletons de module, cf.
    son en-tête) les lookups joueur/tournoi/liste — sans ce reset, un test
    pourrait lire une réponse mise en cache par un test précédent au lieu
    d'exercer le FakeAsyncClient de CE test."""
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


class FakeAsyncClient:
    """Reproduit `async with httpx.AsyncClient(...) as client: await client.get(...)`."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        if url.endswith("/players"):
            search = (params or {}).get("search", "")
            players_by_name = {
                "Carlos Alcaraz": {"id": 1, "name": "Carlos Alcaraz"},
                "Jannik Sinner": {"id": 2, "name": "Jannik Sinner"},
                "Novak Djokovic": {"id": 3, "name": "Novak Djokovic"},
            }
            match = players_by_name.get(search)
            return FakeResponse([match] if match else [])
        if url.endswith("/matches"):
            if params and "player" in params:
                return FakeResponse([
                    {
                        "tournament": "ATP Finals",
                        "tournament_id": "t1",
                        "surface": "Hard",
                        "indoor": True,
                        "round": "SF",
                        "scheduled_time": "2026-11-16T18:00:00Z",
                        "players": {"p1": {"id": 1}, "p2": {"id": 2}},
                    },
                    {
                        # Match impliquant un des deux joueurs mais pas l'autre —
                        # doit être exclu (on veut uniquement les deux joueurs demandés).
                        "tournament": "Autre tournoi",
                        "tournament_id": "t2",
                        "surface": "Clay",
                        "indoor": False,
                        "round": "QF",
                        "scheduled_time": "2026-11-10T12:00:00Z",
                        "players": {"p1": {"id": 1}, "p2": {"id": 3}},
                    },
                    {
                        "tournament": "Masters 1000",
                        "tournament_id": "t3",
                        "surface": "Hard",
                        "indoor": False,
                        "round": "R32",
                        "scheduled_time": "2026-10-01T15:00:00Z",
                        "players": {"p1": {"id": 2}, "p2": {"id": 1}},
                    },
                ])
            # Liste large (page "Matchs à venir") : pas de filtre `player`.
            return FakeResponse([
                {
                    "tournament": "ATP Finals",
                    "tournament_id": "t1",
                    "tour": "atp",
                    "surface": "Hard",
                    "indoor": True,
                    "round": "SF",
                    "is_doubles": False,
                    "scheduled_time": "2026-11-16T18:00:00Z",
                    "players": {
                        "p1": {"id": 1, "name": "Carlos Alcaraz", "country": "ESP", "ranking": 1},
                        "p2": {"id": 2, "name": "Jannik Sinner", "country": "ITA", "ranking": 2},
                    },
                },
                {
                    # Double — doit être exclu (l'app ne prédit que du simple).
                    "tournament": "ATP Finals",
                    "tournament_id": "t1",
                    "tour": "atp",
                    "surface": "Hard",
                    "indoor": True,
                    "round": "SF",
                    "is_doubles": True,
                    "scheduled_time": "2026-11-16T20:00:00Z",
                    "players": {"p1": {"id": 4, "name": "Duo A"}, "p2": {"id": 5, "name": "Duo B"}},
                },
                {
                    "tournament": "Masters 1000",
                    "tournament_id": "t3",
                    "tour": "atp",
                    "surface": "Hard",
                    "indoor": False,
                    "round": "R32",
                    "is_doubles": False,
                    "scheduled_time": "2026-10-01T15:00:00Z",
                    "players": {
                        "p1": {"id": 2, "name": "Jannik Sinner", "country": "ITA", "ranking": 2},
                        "p2": {"id": 3, "name": "Novak Djokovic", "country": "SRB", "ranking": 5},
                    },
                },
            ])
        if "/tournaments/" in url:
            city_by_tournament = {"t1": "Turin", "t3": "Paris"}
            tid = url.rsplit("/", 1)[-1]
            return FakeResponse({"city": city_by_tournament.get(tid)})
        raise AssertionError(f"URL inattendue dans le test : {url}")


def test_get_upcoming_between_filters_and_sorts(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    matches = asyncio.run(client.get_upcoming_between("Carlos Alcaraz", "Jannik Sinner"))

    # Les deux matchs Alcaraz-Sinner, triés par date la plus proche d'abord.
    assert len(matches) == 2
    assert matches[0]["tournament"] == "Masters 1000"
    assert matches[0]["city"] == "Paris"
    assert matches[1]["tournament"] == "ATP Finals"
    assert matches[1]["city"] == "Turin"
    assert matches[1]["indoor"] is True


def test_get_upcoming_between_unknown_player_returns_empty(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    matches = asyncio.run(client.get_upcoming_between("Carlos Alcaraz", "Joueur Inconnu"))
    assert matches == []


def test_get_upcoming_list_excludes_doubles_and_sorts(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "fake-key")

    client = livetennis_client.LiveTennisApiClient()
    matches = asyncio.run(client.get_upcoming_list())

    # Le double est exclu ; il reste 2 matchs, triés par date la plus proche.
    assert len(matches) == 2
    assert matches[0]["tournament"] == "Masters 1000"
    assert matches[0]["player1_name"] == "Jannik Sinner"
    assert matches[0]["player2_ranking"] == 5
    assert matches[1]["tournament"] == "ATP Finals"
    assert matches[1]["player1_country"] == "ESP"


def test_is_configured_reflects_settings_key(monkeypatch):
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "")
    assert livetennis_client.is_configured() is False
    monkeypatch.setattr(livetennis_client.settings, "livetennisapi_key", "abc")
    assert livetennis_client.is_configured() is True
