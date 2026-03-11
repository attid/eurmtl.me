from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from db.sql_models import User
from other.grist_tools import (
    GristAPI,
    GristTableConfig,
    get_grist_asset_by_code,
    get_secretaries,
    load_user_from_grist,
    load_users_from_grist,
)


@pytest.mark.asyncio
async def test_grist_api_fetch_and_load_table_data_builds_urls():
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(
            return_value=SimpleNamespace(
                status=200,
                data={"records": [{"id": 1, "fields": {"TITLE": "One"}}]},
            )
        )
    )
    api = GristAPI(session_manager=session_manager)
    table = GristTableConfig("doc", "Table", base_url="https://example.test")

    records = await api.fetch_data(table, sort="TITLE", filter_dict={"TGID": [1]})
    loaded = await api.load_table_data(table)

    assert records == [{"id": 1, "TITLE": "One"}]
    assert loaded == [{"id": 1, "TITLE": "One"}]
    called_url = session_manager.get_web_request.await_args_list[0].kwargs["url"]
    assert "sort=TITLE" in called_url
    assert "filter=" in called_url


@pytest.mark.asyncio
async def test_grist_api_write_methods_and_load_error_path():
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(
            side_effect=[
                SimpleNamespace(status=200, data={}),
                SimpleNamespace(status=200, data={}),
                SimpleNamespace(status=200, data={}),
                SimpleNamespace(status=500, data={}),
            ]
        )
    )
    api = GristAPI(session_manager=session_manager)
    table = GristTableConfig("doc", "Table")

    assert await api.put_data(table, {"records": []}) is True
    assert await api.patch_data(table, {"records": []}) is True
    assert await api.post_data(table, {"records": []}) is True
    assert await api.load_table_data(table) is None


@pytest.mark.asyncio
async def test_grist_cache_based_helpers():
    user_record = {"telegram_id": 10, "account_id": "GA1", "username": "alice"}
    second_user = {"telegram_id": 11, "account_id": "GA2", "username": "bob"}

    fake_cache = SimpleNamespace(
        find_by_index=lambda table, key, index_name="account_id": (
            {"code": "EURMTL", "need_QR": True}
            if table == "EURMTL_assets"
            else user_record
            if key in {"GA1", "10"}
            else second_user
            if key == "GA2"
            else None
        ),
        get_table_data=lambda table: {
            "EURMTL_secretaries": [{"account": 1, "users": [101, 102]}],
            "EURMTL_accounts": [{"id": 1, "account_id": "GA1"}],
            "EURMTL_users": [
                {"id": 101, "telegram_id": 10},
                {"id": 102, "telegram_id": 11},
            ],
        }.get(table, []),
    )

    with (
        patch("other.grist_tools.grist_cash.get", AsyncMock(return_value=None)),
        patch("other.grist_tools.grist_cash.set", AsyncMock()),
        patch("other.grist_cache.grist_cache", fake_cache),
    ):
        asset = await get_grist_asset_by_code("EURMTL")
        secretaries = await get_secretaries()
        user = await load_user_from_grist(account_id="GA1")
        by_tg = await load_user_from_grist(telegram_id=10)
        users = await load_users_from_grist(["GA1", "GA2"])

    assert asset == {"code": "EURMTL", "need_QR": True}
    assert secretaries == {"GA1": [10, 11]}
    assert isinstance(user, User)
    assert by_tg.account_id == "GA1"
    assert sorted(users.keys()) == ["GA1", "GA2"]
