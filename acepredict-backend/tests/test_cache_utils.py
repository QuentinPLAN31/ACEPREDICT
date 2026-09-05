"""
Tests unitaires de services/cache_utils.py :: TTLCache — utilisé par
weather_providers.py, livetennis_client.py et polymarket_service.py pour
respecter les quotas gratuits des APIs externes.
"""
import asyncio
import time

from app.services.cache_utils import TTLCache


def test_set_then_get_returns_value_within_ttl():
    cache = TTLCache(ttl_seconds=60)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    assert cache.has("k") is True


def test_get_returns_none_for_missing_key():
    cache = TTLCache(ttl_seconds=60)
    assert cache.get("missing") is None
    assert cache.has("missing") is False


def test_entry_expires_after_ttl():
    cache = TTLCache(ttl_seconds=0.05)
    cache.set("k", "v")
    assert cache.has("k") is True
    time.sleep(0.08)
    assert cache.has("k") is False
    assert cache.get("k") is None


def test_none_value_is_cached_and_distinguishable_from_missing():
    # Une dégradation gracieuse (pas de résultat trouvé) doit rester en
    # cache comme un résultat valide -- sinon chaque requête suivante
    # retenterait l'appel réseau pendant tout le TTL.
    cache = TTLCache(ttl_seconds=60)
    cache.set("k", None)
    assert cache.has("k") is True
    assert cache.get("k") is None


def test_get_or_set_sync_computes_once():
    cache = TTLCache(ttl_seconds=60)
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return "computed"

    assert cache.get_or_set_sync("k", compute) == "computed"
    assert cache.get_or_set_sync("k", compute) == "computed"
    assert calls["n"] == 1


def test_get_or_set_async_computes_once():
    cache = TTLCache(ttl_seconds=60)
    calls = {"n": 0}

    async def compute():
        calls["n"] += 1
        return "computed"

    async def run_twice():
        a = await cache.get_or_set_async("k", compute)
        b = await cache.get_or_set_async("k", compute)
        return a, b

    a, b = asyncio.run(run_twice())
    assert a == b == "computed"
    assert calls["n"] == 1


def test_clear_removes_all_entries():
    cache = TTLCache(ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.has("a") is False
    assert cache.has("b") is False
