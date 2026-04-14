from unittest.mock import AsyncMock, patch

import pytest
from stellar_sdk import Keypair

from services.contracts.handlers.mountain_contract import (
    MOUNTAIN_CONTRACT_ID,
    choose_candidate_address,
    load_message,
    prepare_capture_flow,
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
