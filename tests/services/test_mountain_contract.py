from unittest.mock import AsyncMock, patch

import pytest
from stellar_sdk import Keypair

from services.contracts.handlers.mountain_contract import (
    MOUNTAIN_CONTRACT_ID,
    choose_candidate_address,
    format_raw_amount_to_eurmtl,
    load_range,
    load_message,
    prepare_capture_flow,
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
async def test_load_range_returns_normalized_raw_and_eurmtl_values():
    with patch(
        "services.contracts.handlers.mountain_contract.read_contract_value",
        new=AsyncMock(return_value={"vec": [{"i128": "10000000"}, {"i128": "25000000"}]}),
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
