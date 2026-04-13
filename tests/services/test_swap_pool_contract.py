from unittest.mock import AsyncMock, patch

import pytest

from services.contracts.handlers.swap_pool_contract import (
    SWAP_POOL_CONTRACT_ID,
    apply_exact_in_slippage,
    apply_exact_out_slippage,
    format_token_amount,
    human_to_token_amount,
    load_pool_overview,
    normalize_swap_direction,
    prepare_swap_exact_in_flow,
    prepare_swap_exact_out_flow,
    validate_swap_exact_in_form,
    validate_swap_exact_out_form,
)
from services.contracts.registry import get_contract


def test_swap_pool_contract_is_present_in_registry():
    contract = get_contract(SWAP_POOL_CONTRACT_ID)

    assert contract is not None
    assert contract["title"] == "USDM / EURMTL Swap"


def test_swap_pool_contract_declares_overview_exact_in_and_exact_out_blocks():
    contract = get_contract(SWAP_POOL_CONTRACT_ID)

    assert [block["name"] for block in contract["blocks"]] == [
        "pool_overview",
        "exact_in",
        "exact_out",
    ]


def test_human_to_token_amount_uses_7_decimals():
    assert human_to_token_amount("1") == 10_000_000
    assert human_to_token_amount("0.1") == 1_000_000
    assert human_to_token_amount("0,1") == 1_000_000
    assert human_to_token_amount("12.3456789") == 123_456_789


def test_format_token_amount_uses_7_decimals():
    assert format_token_amount(10_000_000) == "1"
    assert format_token_amount(1_000_000) == "0.1"
    assert format_token_amount(123_456_789) == "12.3456789"


def test_normalize_swap_direction_maps_labels_to_indices():
    assert normalize_swap_direction("USDM", "EURMTL") == (0, 1)
    assert normalize_swap_direction("EURMTL", "USDM") == (1, 0)


def test_validate_swap_exact_in_form_requires_valid_address_and_positive_amount():
    assert validate_swap_exact_in_form("", "1") == "user and amount are required"
    assert (
        validate_swap_exact_in_form(
            "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF", "1,5"
        )
        == ""
    )
    assert (
        validate_swap_exact_in_form("GBAD", "1")
        == "user must be a valid Stellar address"
    )
    assert (
        validate_swap_exact_in_form(
            "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF", "0"
        )
        == "amount must be greater than 0"
    )


def test_validate_swap_exact_out_form_requires_valid_address_and_positive_amount():
    assert validate_swap_exact_out_form("", "1") == "user and amount are required"
    assert (
        validate_swap_exact_out_form("GBAD", "1")
        == "user must be a valid Stellar address"
    )


def test_apply_exact_in_slippage_reduces_min_received():
    assert apply_exact_in_slippage("1.1921747", "1") == "1.180253"
    assert apply_exact_in_slippage("1.1921747", "3") == "1.1564095"


def test_apply_exact_out_slippage_increases_max_spent():
    assert apply_exact_out_slippage("1", "1") == "1.01"
    assert apply_exact_out_slippage("1", "5") == "1.05"


@pytest.mark.asyncio
async def test_estimate_swap_exact_in_converts_human_amounts_and_formats_result():
    with patch(
        "services.contracts.handlers.swap_pool_contract.read_contract_value",
        new=AsyncMock(return_value={"u128": "8364215"}),
    ) as read_mock:
        result = await __import__(
            "services.contracts.handlers.swap_pool_contract"
        ).contracts.handlers.swap_pool_contract.estimate_swap_exact_in(
            from_token="USDM",
            to_token="EURMTL",
            amount_in="1",
        )

    assert result == {
        "ok": True,
        "amount_in": "1",
        "estimated_out": "0.8364215",
        "from_token": "USDM",
        "to_token": "EURMTL",
    }
    kwargs = read_mock.await_args.kwargs
    assert kwargs["function_name"] == "estimate_swap"


@pytest.mark.asyncio
async def test_estimate_swap_exact_out_converts_human_amounts_and_formats_result():
    with patch(
        "services.contracts.handlers.swap_pool_contract.read_contract_value",
        new=AsyncMock(return_value={"u128": "11948132"}),
    ) as read_mock:
        result = await __import__(
            "services.contracts.handlers.swap_pool_contract"
        ).contracts.handlers.swap_pool_contract.estimate_swap_exact_out(
            from_token="USDM",
            to_token="EURMTL",
            amount_out="1",
        )

    assert result == {
        "ok": True,
        "amount_out": "1",
        "estimated_in": "1.1948132",
        "from_token": "USDM",
        "to_token": "EURMTL",
    }
    kwargs = read_mock.await_args.kwargs
    assert kwargs["function_name"] == "estimate_swap_strict_receive"


@pytest.mark.asyncio
async def test_prepare_swap_exact_in_flow_builds_sep7_swap_transaction():
    with (
        patch(
            "services.contracts.handlers.swap_pool_contract.estimate_swap_exact_in",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "amount_in": "1",
                    "estimated_out": "0.8364215",
                    "from_token": "USDM",
                    "to_token": "EURMTL",
                }
            ),
        ),
        patch(
            "services.contracts.handlers.swap_pool_contract.prepare_contract_transaction_uri",
            new=AsyncMock(
                return_value={"uri": "web+stellar:tx?xdr=AAAA", "xdr": "AAAA"}
            ),
        ) as prepare_mock,
    ):
        result = await prepare_swap_exact_in_flow(
            user="GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
            from_token="USDM",
            to_token="EURMTL",
            amount_in="1",
            callback_url="https://eurmtl.me/contracts/callback/abc",
            slippage_percent="1",
        )

    assert result == {"uri": "web+stellar:tx?xdr=AAAA", "xdr": "AAAA"}
    kwargs = prepare_mock.await_args.kwargs
    assert kwargs["function_name"] == "swap"
    assert (
        kwargs["source_account_id"]
        == "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
    )
    assert len(kwargs["parameters"]) == 5


@pytest.mark.asyncio
async def test_prepare_swap_exact_out_flow_builds_sep7_strict_receive_transaction():
    with (
        patch(
            "services.contracts.handlers.swap_pool_contract.estimate_swap_exact_out",
            new=AsyncMock(
                return_value={
                    "ok": True,
                    "amount_out": "1",
                    "estimated_in": "1.1948132",
                    "from_token": "USDM",
                    "to_token": "EURMTL",
                }
            ),
        ),
        patch(
            "services.contracts.handlers.swap_pool_contract.prepare_contract_transaction_uri",
            new=AsyncMock(
                return_value={"uri": "web+stellar:tx?xdr=BBBB", "xdr": "BBBB"}
            ),
        ) as prepare_mock,
    ):
        result = await prepare_swap_exact_out_flow(
            user="GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
            from_token="USDM",
            to_token="EURMTL",
            amount_out="1",
            callback_url="https://eurmtl.me/contracts/callback/xyz",
            slippage_percent="3",
        )

    assert result == {"uri": "web+stellar:tx?xdr=BBBB", "xdr": "BBBB"}
    kwargs = prepare_mock.await_args.kwargs
    assert kwargs["function_name"] == "swap_strict_receive"
    assert (
        kwargs["source_account_id"]
        == "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
    )
    assert len(kwargs["parameters"]) == 5


@pytest.mark.asyncio
async def test_load_pool_overview_formats_read_only_contract_data():
    with patch(
        "services.contracts.handlers.swap_pool_contract.read_contract_value",
        new=AsyncMock(
            side_effect=[
                {"symbol": "StandardLiquidityPool"},
                {"symbol": "constant_product"},
                {
                    "vec": [
                        {
                            "address": "CDKLJRIL7E2OWHTPTIHCAXTXI6PEXFOS6PJFAFCDBYWDT3B3QI42EOJA"
                        },
                        {
                            "address": "CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK"
                        },
                    ]
                },
                {"vec": [{"u128": "17214781021"}, {"u128": "14415383509"}]},
                {"u32": 10},
            ]
        ),
    ):
        overview = await load_pool_overview()

    assert overview["contract_name"] == "StandardLiquidityPool"
    assert overview["pool_type"] == "constant_product"
    assert overview["tokens"] == ["USDM", "EURMTL"]
    assert overview["reserves"] == ["1721.4781021", "1441.5383509"]
    assert overview["fee_fraction"] == 10
