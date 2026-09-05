"""
Petit cache TTL en mémoire, partagé par les services qui appellent des API
tierces à quota limité (LiveTennisAPI : 30 req/min et 100 req/jour ; les
fournisseurs météo ont eux aussi des plans gratuits limités). Pas de
Redis/Memcached ici — un seul processus backend pour ce projet, un dict en
mémoire suffit largement et évite une dépendance externe supplémentaire.
Même logique que le cache déjà utilisé dans polymarket_service.py, factorisée
ici pour être réutilisée par les autres services (voir weather_providers.py
et livetennis_client.py).

Usage synchrone (météo) :
    _cache = TTLCache(ttl_seconds=1800)
    value = _cache.get_or_set_sync(key, lambda: _appel_reseau_couteux())

Usage asynchrone (LiveTennisAPI, appels httpx.AsyncClient) :
    value = await _cache.get_or_set_async(key, _coroutine_couteuse)

`has(key)` existe séparément de `get(key)` pour permettre de mettre None en
cache (une dégradation gracieuse — "pas de résultat" — est un résultat valide
à mémoriser, pour ne pas retenter l'appel réseau à chaque requête suivante
pendant toute la durée du TTL).
"""
import time
from typing import Any, Awaitable, Callable, Hashable, Optional


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = ttl_seconds
        self._store: dict[Hashable, tuple[float, Any]] = {}

    def has(self, key: Hashable) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False
        ts, _ = entry
        if time.monotonic() - ts >= self.ttl_seconds:
            del self._store[key]
            return False
        return True

    def get(self, key: Hashable) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts >= self.ttl_seconds:
            del self._store[key]
            return None
        return value

    def set(self, key: Hashable, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def get_or_set_sync(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        if self.has(key):
            return self.get(key)
        value = compute()
        self.set(key, value)
        return value

    async def get_or_set_async(self, key: Hashable, compute: Callable[[], Awaitable[Any]]) -> Any:
        if self.has(key):
            return self.get(key)
        value = await compute()
        self.set(key, value)
        return value

    def clear(self) -> None:
        self._store.clear()
