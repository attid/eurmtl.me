from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from db.sql_models import User
from other.grist_tools import (
    GristAPI,
    GristTableConfig,
    extract_record_ids_from_grist_webhook,
    get_grist_asset_by_code,
    get_secretaries,
    load_user_from_grist,
    load_users_from_grist,
    send_notify_message_record,
    should_send_notify_message_record,
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
            if key in {"GA1", 10}
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


@pytest.mark.asyncio
async def test_load_user_from_grist_uses_integer_telegram_id_index_key():
    user_record = {"telegram_id": 84131737, "account_id": "GA1", "username": "alice"}

    def find_by_index(table, key, index_name="account_id"):
        if table == "EURMTL_users" and index_name == "telegram_id" and key == 84131737:
            return user_record
        return None

    fake_cache = SimpleNamespace(find_by_index=find_by_index)

    with (
        patch("other.grist_tools.grist_cash.get", AsyncMock(return_value=None)),
        patch("other.grist_tools.grist_cash.set", AsyncMock()),
        patch("other.grist_cache.grist_cache", fake_cache),
    ):
        user = await load_user_from_grist(telegram_id=84131737)

    assert isinstance(user, User)
    assert user.account_id == "GA1"


def test_extract_record_ids_from_grist_webhook():
    payload = [
        {"id": 10},
        {"fields": {"id": 11}},
        {"id": "12"},
        {"id": "bad"},
        {},
    ]

    assert extract_record_ids_from_grist_webhook(payload) == [10, 11, 12]
    assert extract_record_ids_from_grist_webhook({}) == []


def test_should_send_notify_message_record():
    assert should_send_notify_message_record({"messsage": "Hi"}) is True
    assert (
        should_send_notify_message_record({"messsage": "", "send_date": None}) is False
    )
    assert (
        should_send_notify_message_record({"messsage": "Hi", "send_date": 1}) is False
    )
    assert (
        should_send_notify_message_record({"messsage": "Hi", "error_message": "boom"})
        is False
    )


@pytest.mark.asyncio
async def test_send_notify_message_record_success_skips_zero_reply_and_topic():
    record = {
        "id": 10,
        "chat_id": -1001429770534,
        "messsage": "<b>Hello</b>",
        "reply_to": 0,
        "topik_id": 0,
        "send_date": None,
        "error_message": "",
    }

    with (
        patch(
            "other.grist_tools.skynet_bot.send_message", new=AsyncMock()
        ) as send_mock,
        patch(
            "other.grist_tools.patch_notify_message_record", new=AsyncMock()
        ) as patch_mock,
    ):
        result = await send_notify_message_record(record)

    assert result == {"status": "sent", "id": 10}
    send_kwargs = send_mock.await_args.kwargs
    assert send_kwargs["chat_id"] == -1001429770534
    assert send_kwargs["text"] == "<b>Hello</b>"
    assert send_kwargs["parse_mode"] == "HTML"
    assert "reply_to_message_id" not in send_kwargs
    assert "message_thread_id" not in send_kwargs
    patch_mock.assert_awaited_once()
    assert "send_date" in patch_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_send_notify_message_record_success_uses_reply_and_topic():
    record = {
        "id": 11,
        "chat_id": -1001429770534,
        "messsage": "<b>Hello</b>",
        "reply_to": 160275,
        "topik_id": 9,
        "send_date": None,
        "error_message": "",
    }

    with (
        patch(
            "other.grist_tools.skynet_bot.send_message", new=AsyncMock()
        ) as send_mock,
        patch(
            "other.grist_tools.patch_notify_message_record", new=AsyncMock()
        ) as patch_mock,
    ):
        result = await send_notify_message_record(record)

    assert result == {"status": "sent", "id": 11}
    send_kwargs = send_mock.await_args.kwargs
    assert send_kwargs["reply_to_message_id"] == 160275
    assert send_kwargs["message_thread_id"] == 9
    patch_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_notify_message_record_failure_writes_error():
    record = {
        "id": 12,
        "chat_id": -1001429770534,
        "messsage": "<b>Hello</b>",
        "reply_to": 160275,
        "topik_id": 0,
        "send_date": None,
        "error_message": "",
    }

    with (
        patch(
            "other.grist_tools.skynet_bot.send_message",
            new=AsyncMock(side_effect=RuntimeError("telegram failed")),
        ),
        patch(
            "other.grist_tools.patch_notify_message_record", new=AsyncMock()
        ) as patch_mock,
    ):
        result = await send_notify_message_record(record)

    assert result == {"status": "failed", "id": 12, "error": "telegram failed"}
    patch_mock.assert_awaited_once_with(12, {"error_message": "telegram failed"})


@pytest.mark.asyncio
async def test_send_notify_message_record_skips_already_processed_record():
    record = {
        "id": 13,
        "chat_id": -1001429770534,
        "messsage": "<b>Hello</b>",
        "reply_to": 0,
        "topik_id": 0,
        "send_date": 1776204000,
        "error_message": "",
    }

    with (
        patch(
            "other.grist_tools.skynet_bot.send_message", new=AsyncMock()
        ) as send_mock,
        patch(
            "other.grist_tools.patch_notify_message_record", new=AsyncMock()
        ) as patch_mock,
    ):
        result = await send_notify_message_record(record)

    assert result == {"status": "skipped", "id": 13}
    send_mock.assert_not_awaited()
    patch_mock.assert_not_awaited()
