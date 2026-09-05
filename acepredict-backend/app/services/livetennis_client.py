"""
Client pour livetennisapi.com — scores live, calendrier, classements en
temps réel (gratuit, sans carte bancaire, ~30 req/min / 100 req/jour,
cf. https://livetennisapi.com/subscribe/free).

SofaScore (endpoints JSON non-officiels) est volontairement absent ici :
gardé uniquement comme fallback de prototypage rapide, à ne jamais mettre
en prod car non garanti dans le temps (cf. consigne utilisateur). Si besoin,
implémenter un client équivalent dans le même style et le brancher derrière
la même interface `LiveDataClient`.

get_upcoming_between() est utilisé par GET /matches/upcoming (cf.
routers/matches.py) : le frontend ne demande plus à l'utilisateur de saisir
une ville/date à la main, il propose directement les matchs déjà programmés
entre les deux joueurs choisis (cf. README "Prochains matchs").

Cache agressif obligatoire : le plan gratuit livetennisapi.com est limité à
~30 req/min ET ~100 req/jour (cf. README "Sources de données & APIs"), une
limite de loin la plus serrée des services externes de ce backend. Un
LiveTennisApiClient est recréé à chaque requête HTTP (cf. get_live_client()
plus bas, appelé par routers/matches.py) — le cache ne peut donc PAS être un
attribut d'instance (il serait vide à chaque fois) : les TTLCache ci-dessous
sont des singletons au niveau module, partagés par toutes les instances du
process, comme le cache déjà utilisé dans polymarket_service.py.
"""
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.cache_utils import TTLCache

# Un id/nom de joueur ou la ville d'un tournoi ne changent (quasiment)
# jamais : cache long. La liste des prochains matchs et le classement
# bougent au fil des résultats : cache court, mais suffisant pour absorber
# le trafic de plusieurs utilisateurs consultant la même page en même temps.
_player_id_cache = TTLCache(ttl_seconds=3600)
_player_profile_cache = TTLCache(ttl_seconds=3600)
_tournament_city_cache = TTLCache(ttl_seconds=86400)
_upcoming_list_cache = TTLCache(ttl_seconds=120)
_upcoming_between_cache = TTLCache(ttl_seconds=120)
_rankings_cache = TTLCache(ttl_seconds=3600)


def _reset_all_caches() -> None:
    """Utilisé par les tests pour repartir d'un état propre entre deux cas —
    les caches ci-dessus sont des singletons de module, donc partagés par
    tous les tests du process si on ne les vide pas explicitement."""
    for cache in (_player_id_cache, _player_profile_cache, _tournament_city_cache,
                  _upcoming_list_cache, _upcoming_between_cache, _rankings_cache):
        cache.clear()


class LiveDataClient:
    """Interface commune pour ne pas coupler les routers à un fournisseur précis."""

    async def get_live_scores(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_upcoming(self, competition_id: Optional[str] = None) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_rankings(self, tour: str = "atp") -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_upcoming_between(self, name1: str, name2: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_upcoming_list(self, tour: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_player_profile(self, name: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    async def get_tournament_city(self, tournament_id: Optional[str]) -> Optional[str]:
        raise NotImplementedError


def is_configured() -> bool:
    return bool(settings.livetennisapi_key)


def _scheduled_sort_key(item: dict[str, Any]):
    """Trie une liste de matchs par date programmée croissante (les matchs
    sans date connue passent en dernier plutôt que de casser le tri)."""
    ts = item.get("scheduled_time")
    if not ts:
        return datetime.max.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


class LiveTennisApiClient(LiveDataClient):
    def __init__(self):
        self.base_url = settings.livetennisapi_base_url
        self.api_key = settings.livetennisapi_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def get_live_scores(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/matches", params={"status": "live"}, headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def get_upcoming(self, competition_id: Optional[str] = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"status": "upcoming"}
        if competition_id:
            params["tournament_id"] = competition_id
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/matches", params=params, headers=self._headers())
            r.raise_for_status()
            return r.json()

    async def get_rankings(self, tour: str = "atp") -> list[dict[str, Any]]:
        async def _fetch():
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/players", params={"tour": tour}, headers=self._headers())
                r.raise_for_status()
                return r.json()
        return await _rankings_cache.get_or_set_async(tour, _fetch)

    async def _find_player_id(self, client: httpx.AsyncClient, name: str) -> Optional[int]:
        """Cherche le joueur par nom sur livetennisapi (GET /players?search=...).
        Prend le premier résultat — les noms de joueurs ATP/WTA top niveau sont
        rarement ambigus, et une erreur ici dégrade juste vers "pas de match
        trouvé" plutôt que de casser l'analyse (cf. get_upcoming_between)."""
        async def _fetch():
            r = await client.get(f"{self.base_url}/players", params={"search": name, "limit": 3}, headers=self._headers())
            r.raise_for_status()
            results = r.json()
            items = results.get("data", results) if isinstance(results, dict) else results
            if not items:
                return None
            return items[0].get("id")
        return await _player_id_cache.get_or_set_async(name.strip().lower(), _fetch)

    async def _get_tournament_city(self, client: httpx.AsyncClient, tournament_id: Optional[str]) -> Optional[str]:
        if not tournament_id:
            return None

        async def _fetch():
            try:
                r = await client.get(f"{self.base_url}/tournaments/{tournament_id}", headers=self._headers())
                r.raise_for_status()
                data = r.json()
                return data.get("city")
            except Exception:
                # Le détail tournoi (ville) est un bonus pour la météo — jamais
                # bloquant : sans ville, l'analyse tourne juste sans ajustement météo.
                return None
        return await _tournament_city_cache.get_or_set_async(tournament_id, _fetch)

    async def get_player_profile(self, name: str) -> Optional[dict[str, Any]]:
        """Fiche joueur brute (GET /players?search=...), utilisée pour
        l'auto-discovery (cf. scripts/sync_hourly.py) : c'est la "source
        secondaire" pour un joueur inconnu de notre base ATP/WTA principale
        — LiveTennisAPI couvre aussi Challenger/ITF (cf. son propre
        descriptif), contrairement à TennisExplorer/l'ITF qui n'exposent
        aucune API publique/gratuite exploitable ici (cf. README
        "Synchronisation des données" pour le détail de ce choix). Renvoie
        l'objet brut de la réponse (ranking/pays/main selon ce que l'API
        fournit) ou None si rien trouvé — jamais d'exception."""
        async def _fetch():
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        f"{self.base_url}/players", params={"search": name, "limit": 3}, headers=self._headers(),
                    )
                    r.raise_for_status()
                    results = r.json()
                items = results.get("data", results) if isinstance(results, dict) else results
                return items[0] if items else None
            except Exception:
                return None
        return await _player_profile_cache.get_or_set_async(name.strip().lower(), _fetch)

    async def get_tournament_city(self, tournament_id: Optional[str]) -> Optional[str]:
        """Version publique de _get_tournament_city, utilisable sans ouvrir
        son propre httpx.AsyncClient d'abord (cf. scripts/sync_hourly.py, qui
        interroge la ville de plusieurs tournois indépendamment d'un appel
        /matches en cours)."""
        async with httpx.AsyncClient(timeout=10) as client:
            return await self._get_tournament_city(client, tournament_id)

    async def get_upcoming_between(self, name1: str, name2: str) -> list[dict[str, Any]]:
        """Renvoie les matchs déjà programmés (status=upcoming) où name1 ET
        name2 sont les deux joueurs face à face — pas juste "l'un ou l'autre"
        (le filtre `player=` de l'API renvoie tout match impliquant au moins
        un des IDs demandés, donc on refiltre nous-mêmes)."""
        cache_key = tuple(sorted([name1.strip().lower(), name2.strip().lower()]))

        async def _fetch():
            async with httpx.AsyncClient(timeout=10) as client:
                id1 = await self._find_player_id(client, name1)
                id2 = await self._find_player_id(client, name2)
                if not id1 or not id2 or id1 == id2:
                    return []

                r = await client.get(
                    f"{self.base_url}/matches",
                    params={"status": "upcoming", "player": [id1, id2], "limit": 50},
                    headers=self._headers(),
                )
                r.raise_for_status()
                raw = r.json()
                matches = raw.get("data", raw) if isinstance(raw, dict) else raw

                out = []
                for m in matches:
                    players = m.get("players") or {}
                    p1 = (players.get("p1") or {}).get("id")
                    p2 = (players.get("p2") or {}).get("id")
                    if {p1, p2} != {id1, id2}:
                        continue
                    city = await self._get_tournament_city(client, m.get("tournament_id"))
                    out.append({
                        "scheduled_time": m.get("scheduled_time"),
                        "tournament": m.get("tournament"),
                        "surface": m.get("surface"),
                        "indoor": m.get("indoor"),
                        "round": m.get("round"),
                        "city": city,
                    })

                out.sort(key=_scheduled_sort_key)
                return out

        return await _upcoming_between_cache.get_or_set_async(cache_key, _fetch)

    async def get_upcoming_list(self, tour: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        """Liste large des prochains matchs (page "Matchs à venir" du
        frontend) — PAS de ville (ça coûterait un appel /tournaments par
        tournoi distinct pour potentiellement des dizaines de matchs, alors
        que get_upcoming_between() ci-dessus ne le fait que pour 1-2 matchs
        précis). Simples/doubles : on exclut les doubles, l'app ne prédit
        que du simple (elo_hard/clay/grass n'a de sens que pour du simple)."""
        limit = max(1, min(limit, 200))
        cache_key = (tour, limit)

        async def _fetch():
            params: dict[str, Any] = {"status": "upcoming", "limit": limit}
            if tour:
                params["tour"] = tour
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/matches", params=params, headers=self._headers())
                r.raise_for_status()
                raw = r.json()
            matches = raw.get("data", raw) if isinstance(raw, dict) else raw

            out = []
            for m in matches:
                if m.get("is_doubles"):
                    continue
                players = m.get("players") or {}
                p1 = players.get("p1") or {}
                p2 = players.get("p2") or {}
                out.append({
                    "scheduled_time": m.get("scheduled_time"),
                    "tournament": m.get("tournament"),
                    "tournament_id": m.get("tournament_id"),
                    "tour": m.get("tour"),
                    "surface": m.get("surface"),
                    "indoor": m.get("indoor"),
                    "round": m.get("round"),
                    "player1_name": p1.get("name"),
                    "player1_country": p1.get("country"),
                    "player1_ranking": p1.get("ranking"),
                    "player2_name": p2.get("name"),
                    "player2_country": p2.get("country"),
                    "player2_ranking": p2.get("ranking"),
                })

            out.sort(key=_scheduled_sort_key)
            return out

        return await _upcoming_list_cache.get_or_set_async(cache_key, _fetch)


def get_live_client() -> LiveDataClient:
    return LiveTennisApiClient()
