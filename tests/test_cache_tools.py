from unittest.mock import patch

import pytest

from other.cache_tools import AsyncTTLCache, async_cache_with_ttl


@pytest.mark.asyncio
async def test_async_ttl_cache_get_set_and_invalidate():
    cache = AsyncTTLCache(ttl_seconds=60, maxsize=2)

    await cache.set("a", 1)
    assert await cache.get("a") == 1
    assert await cache.invalidate("a") is True
    assert await cache.get("a") is None
    assert await cache.invalidate("missing") is False


@pytest.mark.asyncio
async def test_async_ttl_cache_expires_and_evicts_oldest():
    cache = AsyncTTLCache(ttl_seconds=10, maxsize=2)

    with patch("other.cache_tools.time", side_effect=[0, 1, 2, 3, 20]):
        await cache.set("a", "first")
        await cache.set("b", "second")
        await cache.set("c", "third")
        assert await cache.get("a") is None

    assert "b" in cache.cache
    assert "c" in cache.cache


@pytest.mark.asyncio
async def test_async_cache_with_ttl_caches_result():
    state = {"calls": 0}

    @async_cache_with_ttl(ttl_seconds=60)
    async def sample(value):
        state["calls"] += 1
        return value * 2

    assert await sample(3) == 6
    assert await sample(3) == 6
    assert state["calls"] == 1
