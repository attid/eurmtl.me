from unittest.mock import AsyncMock, patch

import pytest
from stellar_sdk import Keypair

from services.contracts.handlers.mountain_contract import (
    MOUNTAIN_CONTRACT_ID,
    MOUNTAIN_NOTIFY_CACHE_KEY,
    MOUNTAIN_NOTIFY_CHAT_ID,
    MOUNTAIN_NOTIFY_REPLY_TO,
    MOUNTAIN_NOTIFY_TOPIC_ID,
    choose_candidate_address,
    format_raw_amount_to_eurmtl,
    load_range,
    load_message,
    load_last_mountain_notification_comment,
    mountain_notify_cache,
    notify_mountain_message_change,
    prepare_capture_flow,
    render_mountain_notification_html,
    validate_capture_form,
)
from services.contracts.registry import get_contract


def test_mountain_contract_is_present_in_registry():
    contract = get_contract(MOUNTAIN_CONTRACT_ID)

    assert contract is not None
    assert contract["title"] == "King of the Mountain"


def test_mountain_contract_declares_message_and_capture_blocks():
    contract = get_contract(MOUNTAIN_CONTRACT_ID)

    assert [block["name"] for block in contract["blocks"]] == ["message", "capture"]


def test_capture_block_declares_user_amount_and_msg_fields_in_order():
    contract = get_contract(MOUNTAIN_CONTRACT_ID)
    capture_block = next(
        block for block in contract["blocks"] if block["name"] == "capture"
    )

    assert [field["name"] for field in capture_block["fields"]] == [
        "user",
        "amount",
        "msg",
    ]


def test_choose_candidate_address_prefers_detected_address():
    assert (
        choose_candidate_address(
            detected_address="GDETECTED",
            session_address="GSESSION",
        )
        == "GDETECTED"
    )


def test_choose_candidate_address_falls_back_to_session_address():
    assert (
        choose_candidate_address(
            detected_address=None,
            session_address="GSESSION",
        )
        == "GSESSION"
    )


def test_choose_candidate_address_returns_empty_string_when_no_address_available():
    assert choose_candidate_address(detected_address=None, session_address=None) == ""


def test_render_mountain_notification_html_escapes_html_and_preserves_newlines():
    rendered = render_mountain_notification_html("Line 1\n<b>Line 2</b> & more")

    assert "<b>У горы сменился message</b>" in rendered
    assert "Line 1\n&lt;b&gt;Line 2&lt;/b&gt; &amp; more" in rendered
    assert f'href="https://eurmtl.me/contracts/{MOUNTAIN_CONTRACT_ID}"' in rendered


@pytest.mark.asyncio
async def test_load_message_uses_soroban_reader_with_contract_and_message_function():
    with patch(
        "services.contracts.handlers.mountain_contract.read_contract_string",
        new=AsyncMock(return_value="Long live the king"),
    ) as read_mock:
        result = await load_message(MOUNTAIN_CONTRACT_ID)

    assert result == {"ok": True, "message": "Long live the king", "error": ""}
    read_mock.assert_awaited_once_with(
        rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
        contract_id=MOUNTAIN_CONTRACT_ID,
        function_name="message",
    )


@pytest.mark.asyncio
async def test_load_message_returns_controlled_error_payload():
    with patch(
        "services.contracts.handlers.mountain_contract.read_contract_string",
        new=AsyncMock(side_effect=ValueError("boom")),
    ):
        result = await load_message(MOUNTAIN_CONTRACT_ID)

    assert result == {"ok": False, "message": "", "error": "boom"}


@pytest.mark.asyncio
async def test_load_last_mountain_notification_comment_uses_latest_matching_record():
    with patch(
        "services.contracts.handlers.mountain_contract.grist_manager.load_table_data",
        new=AsyncMock(
            return_value=[
                {
                    "id": 3,
                    "chat_id": MOUNTAIN_NOTIFY_CHAT_ID,
                    "reply_to": MOUNTAIN_NOTIFY_REPLY_TO,
                    "topik_id": MOUNTAIN_NOTIFY_TOPIC_ID,
                    "messsage": "<b>Другой поток</b>",
                    "comment": "ignore me",
                },
                {
                    "id": 5,
                    "chat_id": MOUNTAIN_NOTIFY_CHAT_ID,
                    "reply_to": MOUNTAIN_NOTIFY_REPLY_TO,
                    "topik_id": MOUNTAIN_NOTIFY_TOPIC_ID,
                    "messsage": "<b>У горы сменился message</b>\nOld",
                    "comment": "old value",
                },
                {
                    "id": 7,
                    "chat_id": MOUNTAIN_NOTIFY_CHAT_ID,
                    "reply_to": MOUNTAIN_NOTIFY_REPLY_TO,
                    "topik_id": MOUNTAIN_NOTIFY_TOPIC_ID,
                    "messsage": "<b>У горы сменился message</b>\nNew",
                    "comment": "new value",
                },
            ]
        ),
    ):
        result = await load_last_mountain_notification_comment()

    assert result == "new value"


@pytest.mark.asyncio
async def test_load_range_returns_normalized_raw_and_eurmtl_values():
    with patch(
        "services.contracts.handlers.mountain_contract.read_contract_value",
        new=AsyncMock(
            return_value={"vec": [{"i128": "10000000"}, {"i128": "25000000"}]}
        ),
    ) as read_mock:
        result = await load_range(MOUNTAIN_CONTRACT_ID)

    assert result == {
        "ok": True,
        "min_amount_raw": "10000000",
        "max_amount_raw": "25000000",
        "min_amount_eurmtl": "1",
        "max_amount_eurmtl": "2.5",
        "error": "",
    }
    read_mock.assert_awaited_once_with(
        contract_id=MOUNTAIN_CONTRACT_ID,
        function_name="get_range",
        rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
    )


@pytest.mark.asyncio
async def test_load_range_returns_controlled_error_payload():
    with patch(
        "services.contracts.handlers.mountain_contract.read_contract_value",
        new=AsyncMock(side_effect=ValueError("boom")),
    ):
        result = await load_range(MOUNTAIN_CONTRACT_ID)

    assert result == {
        "ok": False,
        "min_amount_raw": "",
        "max_amount_raw": "",
        "min_amount_eurmtl": "",
        "max_amount_eurmtl": "",
        "error": "boom",
    }


@pytest.mark.asyncio
async def test_notify_mountain_message_change_posts_new_grist_record_when_message_changed():
    await mountain_notify_cache.invalidate(MOUNTAIN_NOTIFY_CACHE_KEY)

    with (
        patch(
            "services.contracts.handlers.mountain_contract.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "services.contracts.handlers.mountain_contract.grist_manager.post_data",
            new=AsyncMock(return_value=True),
        ) as post_mock,
    ):
        result = await notify_mountain_message_change("Line 1\nLine 2")

    assert result == {"created": True, "reason": "posted", "error": ""}
    post_mock.assert_awaited_once()
    payload = post_mock.await_args.args[1]
    fields = payload["records"][0]["fields"]
    assert fields["chat_id"] == MOUNTAIN_NOTIFY_CHAT_ID
    assert fields["reply_to"] == MOUNTAIN_NOTIFY_REPLY_TO
    assert fields["topik_id"] == MOUNTAIN_NOTIFY_TOPIC_ID
    assert fields["comment"] == "Line 1\nLine 2"
    assert "Line 1\nLine 2" in fields["messsage"]


@pytest.mark.asyncio
async def test_notify_mountain_message_change_skips_when_same_value_is_in_grist():
    await mountain_notify_cache.invalidate(MOUNTAIN_NOTIFY_CACHE_KEY)

    with (
        patch(
            "services.contracts.handlers.mountain_contract.grist_manager.load_table_data",
            new=AsyncMock(
                return_value=[
                    {
                        "id": 1,
                        "chat_id": MOUNTAIN_NOTIFY_CHAT_ID,
                        "reply_to": MOUNTAIN_NOTIFY_REPLY_TO,
                        "topik_id": MOUNTAIN_NOTIFY_TOPIC_ID,
                        "messsage": "<b>У горы сменился message</b><br>same",
                        "comment": "same",
                    }
                ]
            ),
        ),
        patch(
            "services.contracts.handlers.mountain_contract.grist_manager.post_data",
            new=AsyncMock(return_value=True),
        ) as post_mock,
    ):
        result = await notify_mountain_message_change("same")

    assert result == {"created": False, "reason": "grist", "error": ""}
    post_mock.assert_not_awaited()
    assert await mountain_notify_cache.get(MOUNTAIN_NOTIFY_CACHE_KEY) == "same"


@pytest.mark.asyncio
async def test_notify_mountain_message_change_skips_when_same_value_is_in_cache():
    await mountain_notify_cache.set(MOUNTAIN_NOTIFY_CACHE_KEY, "cached")

    with (
        patch(
            "services.contracts.handlers.mountain_contract.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch(
            "services.contracts.handlers.mountain_contract.grist_manager.post_data",
            new=AsyncMock(return_value=True),
        ) as post_mock,
    ):
        result = await notify_mountain_message_change("cached")

    assert result == {"created": False, "reason": "cache", "error": ""}
    load_mock.assert_not_awaited()
    post_mock.assert_not_awaited()


def test_format_raw_amount_to_eurmtl_converts_7_decimals():
    assert format_raw_amount_to_eurmtl("10000000") == "1"
    assert format_raw_amount_to_eurmtl("25000000") == "2.5"
    assert format_raw_amount_to_eurmtl("1") == "0.0000001"


def test_validate_capture_form_rejects_amount_below_range():
    user = Keypair.random().public_key

    assert (
        validate_capture_form(
            user=user,
            amount="9",
            msg="For glory",
            min_amount_raw="10",
            max_amount_raw="20",
        )
        == "amount must be between 10 and 20 raw units"
    )


def test_validate_capture_form_rejects_amount_above_range():
    user = Keypair.random().public_key

    assert (
        validate_capture_form(
            user=user,
            amount="21",
            msg="For glory",
            min_amount_raw="10",
            max_amount_raw="20",
        )
        == "amount must be between 10 and 20 raw units"
    )


@pytest.mark.asyncio
async def test_prepare_capture_flow_builds_single_capture_transaction():
    user = Keypair.random().public_key

    with patch(
        "services.contracts.handlers.mountain_contract.prepare_contract_transaction_uri",
        new=AsyncMock(return_value={"uri": "web+stellar:tx?xdr=AAAA", "xdr": "AAAA"}),
    ) as prepare_mock:
        result = await prepare_capture_flow(
            contract_id=MOUNTAIN_CONTRACT_ID,
            user=user,
            amount="100",
            msg="For glory",
            callback_url="https://eurmtl.me/contracts/callback/123",
        )

    assert result == {"uri": "web+stellar:tx?xdr=AAAA", "xdr": "AAAA"}
    kwargs = prepare_mock.await_args.kwargs
    assert kwargs["contract_id"] == MOUNTAIN_CONTRACT_ID
    assert kwargs["source_account_id"] == user
    assert kwargs["function_name"] == "capture"
    assert kwargs["token_contract_id"] is None
    assert kwargs["approve_expiration_ledger_offset"] is None
