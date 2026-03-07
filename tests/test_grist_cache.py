from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from other.grist_cache import GristCacheManager


@pytest.mark.asyncio
async def test_load_table_to_cache_builds_main_and_additional_indexes():
    cache = GristCacheManager()
    records = [
        {"account_id": "G1", "telegram_id": 100, "name": "Alice"},
        {"account_id": "G2", "telegram_id": 200, "name": "Bob"},
    ]

    with patch("other.grist_tools.MTLGrist", new=SimpleNamespace(EURMTL_users="users")):
        with patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=records),
        ):
            await cache.load_table_to_cache("EURMTL_users")

    assert cache.get_table_data("EURMTL_users") == records
    assert cache.find_by_index("EURMTL_users", "G1") == records[0]
    assert cache.find_by_index("EURMTL_users", 200, field="telegram_id") == records[1]


@pytest.mark.asyncio
async def test_load_table_to_cache_ignores_empty_data():
    cache = GristCacheManager()

    with patch("other.grist_tools.MTLGrist", new=SimpleNamespace(EURMTL_users="users")):
        with patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ):
            await cache.load_table_to_cache("EURMTL_users")

    assert cache.get_table_data("EURMTL_users") == []
    assert cache.find_by_index("EURMTL_users", "missing") is None


@pytest.mark.asyncio
async def test_initialize_cache_loads_all_tables_and_continues_after_error():
    cache = GristCacheManager()

    async def fake_load(table_name):
        if table_name == "EURMTL_assets":
            raise RuntimeError("boom")
        cache.caches[table_name] = [{"table": table_name}]

    with patch.object(
        cache, "load_table_to_cache", new=AsyncMock(side_effect=fake_load)
    ):
        await cache.initialize_cache()

    assert cache.get_table_data("GRIST_access") == [{"table": "GRIST_access"}]
    assert cache.get_table_data("EURMTL_assets") == []


@pytest.mark.asyncio
async def test_update_cache_by_webhook_skips_unknown_table():
    cache = GristCacheManager()

    with patch.object(cache, "load_table_to_cache", new=AsyncMock()) as load_mock:
        await cache.update_cache_by_webhook("UNKNOWN")

    load_mock.assert_not_called()


@pytest.mark.asyncio
async def test_update_cache_by_webhook_reloads_known_table():
    cache = GristCacheManager()

    with patch.object(cache, "load_table_to_cache", new=AsyncMock()) as load_mock:
        await cache.update_cache_by_webhook("EURMTL_assets")

    load_mock.assert_awaited_once_with("EURMTL_assets")


def test_filter_helpers_return_expected_records():
    cache = GristCacheManager(
        caches={
            "EURMTL_assets": [
                {"code": "EURMTL", "issuer": "G1", "enabled": True},
                {"code": "USDM", "issuer": "G2", "enabled": False},
            ]
        }
    )

    assert cache.find_by_filter("EURMTL_assets", "code", ["EURMTL"]) == [
        {"code": "EURMTL", "issuer": "G1", "enabled": True}
    ]
    assert cache.find_one_by_filter("EURMTL_assets", "issuer", "G2") == {
        "code": "USDM",
        "issuer": "G2",
        "enabled": False,
    }
    assert cache.find_one_by_filter("EURMTL_assets", "issuer", "missing") is None
