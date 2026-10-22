import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from stellar_sdk import (
    Account,
    Keypair,
    LiquidityPoolWithdraw,
    Network,
    PathPaymentStrictSend,
    Payment,
    TransactionEnvelope,
)

YANDEX_METRICA_JS = "https://mc.yandex.ru/metrika/tag.js"
YANDEX_METRICA_PIXEL = "https://mc.yandex.ru/watch/95900394"

ACCOUNT = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
OTHER_ACCOUNT = "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
ASSET = f"EURMTL-{ACCOUNT}"


@pytest.mark.asyncio
async def test_lab_root(client):
    """Test /lab"""
    response = await client.get("/lab")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_lab_root_disables_third_party_analytics(client):
    """Test /lab does not run analytics JS next to local signing keys."""
    response = await client.get("/lab")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert YANDEX_METRICA_JS not in body
    assert YANDEX_METRICA_PIXEL in body


@pytest.mark.asyncio
async def test_lab_root_renders_all_operations_tab_with_filter(client):
    response = await client.get("/lab")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert ">All<" in body
    assert 'id="operation-all-filter"' in body
    assert 'id="operation-all"' in body
    assert 'value="payment"' in body
    assert 'value="begin_sponsoring_future_reserves"' in body


@pytest.mark.asyncio
async def test_lab_mtl_accounts(client):
    """Test /lab/mtl_accounts"""
    mock_accounts = [
        {"description": "Test", "account_id": "GABCDEFGHIJKLMNOPQRSTUVWXYZ123456"}
    ]
    with patch(
        "routers.laboratory.grist_manager.load_table_data",
        new=AsyncMock(return_value=mock_accounts),
    ):
        response = await client.get("/lab/mtl_accounts")
        assert response.status_code == 200
        data = await response.get_json()
        assert any("Test" in k for k in data.keys())


@pytest.mark.asyncio
async def test_lab_sequence(client):
    """Test /lab/sequence/<account_id>"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.data = {"sequence": "100"}

    with patch(
        "routers.laboratory.http_session_manager.get_web_request",
        new=AsyncMock(return_value=mock_response),
    ):
        response = await client.get("/lab/sequence/GABC")
        assert response.status_code == 200
        data = await response.get_json()
        assert data["sequence"] == "101"


@pytest.mark.asyncio
async def test_lab_mtl_assets(client):
    """Test /lab/mtl_assets"""
    mock_assets = [{"code": "EURMTL", "issuer": "GABC"}]
    with patch(
        "routers.laboratory.grist_manager.load_table_data",
        new=AsyncMock(return_value=mock_assets),
    ):
        response = await client.get("/lab/mtl_assets")
        assert response.status_code == 200
        data = await response.get_json()
        assert "EURMTL-GABC" in data.values()


@pytest.mark.asyncio
async def test_lab_check_balance(client):
    """Test /lab/check_balance"""
    mock_account = {"balances": [{"asset_type": "native", "balance": "100.0"}]}

    with patch("routers.laboratory.Server") as MockServer:
        mock_server = MockServer.return_value
        mock_server.accounts.return_value.account_id.return_value.call = MagicMock(
            return_value=mock_account
        )

        response = await client.post(
            "/lab/check_balance",
            json={
                "account_id": "GABC1234567890123456789012345678901234567890123456789012",
                "asset": "XLM",
            },
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["balance"] == "100.0"


@pytest.mark.asyncio
async def test_lab_mtl_pools_uses_cache(client):
    mock_pools = [
        {"need_dropdown": True, "info": "Pool A", "pool_id": "pool-a"},
        {"need_dropdown": False, "info": "Pool B", "pool_id": "pool-b"},
    ]

    with patch(
        "other.grist_cache.grist_cache.get_table_data",
        return_value=mock_pools,
    ):
        response = await client.get("/lab/mtl_pools")

    assert response.status_code == 200
    data = await response.get_json()
    assert data == {"Pool A": "pool-a"}


@pytest.mark.asyncio
async def test_lab_build_xdr_rejects_invalid_memo_hash(client):
    response = await client.post(
        "/lab/build_xdr",
        json={"memo_type": "memo_hash", "memo": "bad-hash"},
    )

    assert response.status_code == 200
    assert await response.get_json() == {
        "error": "Bad memo hash. Must be 64 bytes hex string"
    }


@pytest.mark.asyncio
async def test_lab_build_xdr_returns_built_xdr(client):
    with patch(
        "routers.laboratory.stellar_build_xdr",
        new=AsyncMock(return_value="AAAA"),
    ):
        response = await client.post(
            "/lab/build_xdr",
            json={
                "publicKey": ACCOUNT,
                "memo_type": "memo_text",
                "memo": "hello",
                "operations": [],
            },
        )

    assert response.status_code == 200
    assert await response.get_json() == {"xdr": "AAAA"}


@pytest.mark.asyncio
async def test_lab_build_xdr_accepts_missing_memo_type(client):
    with patch(
        "routers.laboratory.stellar_build_xdr",
        new=AsyncMock(return_value="AAAA"),
    ):
        response = await client.post(
            "/lab/build_xdr",
            json={"publicKey": "GABC", "operations": []},
        )

    assert response.status_code == 200
    assert await response.get_json() == {"xdr": "AAAA"}


@pytest.mark.asyncio
async def test_lab_build_xdr_rejects_asset_as_object(client):
    """Sentry #3123: asset пришёл объектом вместо строки -> 400, не 500."""
    build_mock = AsyncMock(return_value="AAAA")
    with patch("routers.laboratory.stellar_build_xdr", new=build_mock):
        response = await client.post(
            "/lab/build_xdr",
            json={
                "publicKey": ACCOUNT,
                "operations": [
                    {
                        "type": "payment",
                        "destination": OTHER_ACCOUNT,
                        "asset": {"code": "'XLM'"},
                        "amount": "10",
                    }
                ],
            },
        )

    assert response.status_code == 400
    error = (await response.get_json())["error"]
    assert "operations[0].asset" in error
    assert "CODE-ISSUER" in error
    assert "dict" in error
    build_mock.assert_not_awaited()


INVALID_BUILD_XDR_PAYLOADS = [
    pytest.param([], "Request body must be a JSON object", id="body-list"),
    pytest.param({"operations": []}, "publicKey is required", id="missing-public-key"),
    pytest.param(
        {"publicKey": {"key": ACCOUNT}, "operations": []},
        "publicKey is required",
        id="public-key-dict",
    ),
    pytest.param(
        {"publicKey": ACCOUNT, "operations": {"type": "payment"}},
        "operations is required and must be an array",
        id="operations-dict",
    ),
    pytest.param(
        {"publicKey": ACCOUNT, "operations": ["payment"]},
        "operations[0] must be a JSON object",
        id="operation-string",
    ),
    pytest.param(
        {"publicKey": ACCOUNT, "operations": [{"asset": "XLM"}]},
        "operations[0].type is required",
        id="operation-missing-type",
    ),
    pytest.param(
        {"publicKey": ACCOUNT, "sequence": "abc", "operations": []},
        "sequence must be an integer",
        id="sequence-not-numeric",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "payment",
                    "destination": OTHER_ACCOUNT,
                    "asset": "EURMTL",
                    "amount": "1",
                }
            ],
        },
        "operations[0].asset must be a string like",
        id="asset-without-issuer",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "payment",
                    "destination": OTHER_ACCOUNT,
                    "asset": "EURMTL-BAD",
                    "amount": "1",
                }
            ],
        },
        "operations[0].asset must be a string like",
        id="asset-bad-issuer",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "payment",
                    "destination": OTHER_ACCOUNT,
                    "asset": ["XLM"],
                    "amount": "1",
                }
            ],
        },
        "operations[0].asset must be a string like",
        id="asset-list",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "payment",
                    "destination": OTHER_ACCOUNT,
                    "asset": "XLM",
                    "amount": {"value": "1"},
                }
            ],
        },
        "operations[0].amount must be a number",
        id="amount-dict",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [{"type": "change_trust", "asset": "XLM", "limit": {"v": 1}}],
        },
        "operations[0].limit must be a string",
        id="change-trust-limit-dict",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [{"type": "manage_data", "data_name": "n", "data_value": 5}],
        },
        "operations[0].data_value must be a string",
        id="manage-data-value-int",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "sell",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "price": "1",
                    "offer_id": None,
                }
            ],
        },
        "operations[0].offer_id must be an integer",
        id="sell-offer-id-null",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    "path": "not-json",
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-not-json",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    "path": '[{"asset_type": "credit_alphanum4", "asset_code": "USD"}]',
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-missing-issuer",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": {"dest_min": "1"},
                    "path": "[]",
                }
            ],
        },
        "operations[0].destination must be a number",
        id="swap-destination-dict",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "create_claimable_balance",
                    "asset": "XLM",
                    "amount": "1",
                    "claimant_1_destination": OTHER_ACCOUNT,
                    "claimant_1_predicate_type": "abs_sometime",
                    "claimant_1_predicate_value": "2026-03-07T18:00:00Z",
                }
            ],
        },
        "operations[0].claimant_1_predicate_type must be one of",
        id="claimant-unknown-predicate",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "create_claimable_balance",
                    "asset": "XLM",
                    "amount": "1",
                    "claimant_1_destination": OTHER_ACCOUNT,
                    "claimant_1_predicate_type": "rel_before",
                    "claimant_1_predicate_value": "tomorrow",
                }
            ],
        },
        "operations[0].claimant_1_predicate_value must be ISO datetime",
        id="claimant-bad-predicate-value",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "revoke_sponsorship",
                    "revoke_type": "trustline",
                    "revoke_trustline_account": OTHER_ACCOUNT,
                    "revoke_trustline_asset": {"code": "XLM"},
                }
            ],
        },
        "operations[0].revoke_trustline_asset must be a string like",
        id="revoke-trustline-asset-dict",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "set_trust_line_flags",
                    "trustor": OTHER_ACCOUNT,
                    "asset": "XLM",
                }
            ],
        },
        "operations[0].setFlags is required",
        id="trust-line-flags-missing-set-flags",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "memo_type": "memo_text",
            "memo": {"t": 1},
            "operations": [],
        },
        "memo is required and must be a string",
        id="memo-text-dict",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    "path": '["XLM"]',
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-element-not-object",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "create_claimable_balance",
                    "asset": "XLM",
                    "amount": "1",
                    "claimant_1_destination": {"account": OTHER_ACCOUNT},
                    "claimant_1_predicate_type": "unconditional",
                }
            ],
        },
        "operations[0].claimant_1_destination must be a string",
        id="claimant-destination-dict",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [{"type": "set_options", "threshold": "1/2"}],
        },
        "operations[0].threshold must be an integer",
        id="threshold-bad-slash-form",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    "path": {"asset_type": "native"},
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-object",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    "path": "{}",
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-not-list",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    "path": (
                        '[{"asset_type": "credit_alphanum4", '
                        '"asset_code": "USD", "asset_issuer": "BAD"}]'
                    ),
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-bad-issuer",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "create_claimable_balance",
                    "asset": "XLM",
                    "amount": "1",
                    "claimant_1_destination": OTHER_ACCOUNT,
                    "claimant_1_predicate_type": "abs_before",
                    "claimant_1_predicate_value": "not-a-date",
                }
            ],
        },
        "operations[0].claimant_1_predicate_value must be ISO datetime",
        id="claimant-bad-abs-datetime",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "create_claimable_balance",
                    "asset": "XLM",
                    "amount": "1",
                    "claimant_1_destination": OTHER_ACCOUNT,
                    "claimant_1_predicate_type": "rel_before",
                    "claimant_1_predicate_value": ["3600"],
                }
            ],
        },
        "operations[0].claimant_1_predicate_value must be a string",
        id="claimant-predicate-value-list",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "create_claimable_balance",
                    "asset": "XLM",
                    "amount": "1",
                    "claimant_1_destination": OTHER_ACCOUNT,
                    "claimant_1_predicate_type": "rel_before",
                    "claimant_1_predicate_value": " ",
                }
            ],
        },
        "operations[0].claimant_1_predicate_value is required",
        id="claimant-predicate-value-empty",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "pay_divs",
                    "holders": ASSET,
                    "asset": "XLM",
                    # pay_divs приводит amount через float(), а не float2str().
                    "amount": "1,5",
                }
            ],
        },
        "operations[0].amount must be a number",
        id="pay-divs-amount-comma",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    # asset_code/issuer валидны, но asset_type отсутствует:
                    # сборщик читает asset["asset_type"] -> KeyError -> 500.
                    "path": f'[{{"asset_code": "USD", "asset_issuer": "{ACCOUNT}"}}]',
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-missing-asset-type",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "swap",
                    "selling": "XLM",
                    "buying": ASSET,
                    "amount": "1",
                    "destination": "1",
                    "path": (
                        '[{"asset_type": {"kind": "native"}, '
                        f'"asset_code": "USD", "asset_issuer": "{ACCOUNT}"}}]'
                    ),
                }
            ],
        },
        "operations[0].path must be a JSON array",
        id="swap-path-asset-type-not-string",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "liquidity_pool_withdraw",
                    "liquidity_pool_id": "a" * 64,
                    # При нулевом минимуме сборщик вызывает float(amount),
                    # а float("1,5") падает -> запятая недопустима.
                    "amount": "1,5",
                    "min_amount_a": "0",
                    "min_amount_b": "1",
                }
            ],
        },
        "operations[0].amount must be a number",
        id="withdraw-comma-amount-zero-min",
    ),
    pytest.param(
        {
            "publicKey": ACCOUNT,
            "operations": [
                {
                    "type": "liquidity_pool_deposit",
                    "liquidity_pool_id": "abc",
                    "max_amount_a": "1",
                    "max_amount_b": "1",
                    "min_price": {"value": 0},
                    "max_price": "1",
                }
            ],
        },
        "operations[0].min_price must be a number",
        id="lp-deposit-min-price-dict",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("payload", "expected_fragment"), INVALID_BUILD_XDR_PAYLOADS)
async def test_lab_build_xdr_rejects_invalid_payload(
    client, payload, expected_fragment
):
    """Неправильные типы/форматы на границе API дают 400 вместо 500."""
    build_mock = AsyncMock(return_value="AAAA")
    with patch("routers.laboratory.stellar_build_xdr", new=build_mock):
        response = await client.post("/lab/build_xdr", json=payload)

    assert response.status_code == 400
    assert expected_fragment in (await response.get_json())["error"]
    build_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_lab_build_xdr_rejects_non_string_memo_hash(client):
    """Нестроковый memo для memo_hash больше не роняет роут в 500."""
    response = await client.post(
        "/lab/build_xdr",
        json={"memo_type": "memo_hash", "memo": {"hash": "AB"}},
    )

    assert response.status_code == 200
    assert await response.get_json() == {
        "error": "Bad memo hash. Must be 64 bytes hex string"
    }


VALID_BUILD_XDR_OPERATIONS = [
    pytest.param(
        [
            {
                "type": "payment",
                "destination": OTHER_ACCOUNT,
                "asset": "XLM",
                "amount": "10",
            },
            {
                "type": "payment",
                "destination": OTHER_ACCOUNT,
                "asset": ASSET,
                "amount": 10,
            },
            {"type": "change_trust", "asset": ASSET, "limit": ""},
        ],
        id="payments-change-trust",
    ),
    pytest.param(
        [
            {
                "type": "sell",
                "selling": ASSET,
                "buying": "XLM",
                "amount": "1",
                "price": "2",
                "offer_id": "1",
            },
            {
                "type": "buy",
                "selling": "XLM",
                "buying": ASSET,
                "amount": 1,
                "price": 2,
                "offer_id": 3,
            },
            {
                "type": "sell_passive",
                "selling": ASSET,
                "buying": "XLM",
                "amount": "1",
                "price": "2",
            },
        ],
        id="offers",
    ),
    pytest.param(
        [
            {
                "type": "swap",
                "selling": "XLM",
                "buying": ASSET,
                "amount": "1",
                "destination": "0.5",
                "path": (
                    '[{"asset_type": "native"}, '
                    '{"asset_type": "credit_alphanum4", '
                    f'"asset_code": "USD", "asset_issuer": "{ACCOUNT}"}}]'
                ),
            },
            {
                "type": "set_trust_line_flags",
                "trustor": OTHER_ACCOUNT,
                "asset": ASSET,
                "setFlags": "1",
                "clearFlags": "",
            },
            {
                "type": "set_options",
                "threshold": "1/2/3",
                "master": "1",
                "home": "eurmtl.me",
            },
        ],
        id="swap-and-flags",
    ),
    pytest.param(
        [
            {
                "type": "create_claimable_balance",
                "asset": "XLM",
                "amount": "1",
                "claimant_1_destination": OTHER_ACCOUNT,
                "claimant_1_predicate_type": "unconditional",
                "claimant_1_predicate_value": "",
                "claimant_2_destination": "",
                "claimant_2_predicate_type": "",
                "claimant_2_predicate_value": "",
            },
            {
                "type": "revoke_sponsorship",
                "revoke_type": "trustline",
                "revoke_trustline_account": OTHER_ACCOUNT,
                "revoke_trustline_asset": ASSET,
            },
            {"type": "bump_sequence", "bump_to": "123"},
        ],
        id="claimable-revoke-bump",
    ),
    pytest.param(
        [
            {"type": "manage_data", "data_name": "name", "data_value": ""},
            {
                "type": "liquidity_pool_trustline",
                "liquidity_pool_id": "abc",
                "limit": "",
            },
            {"type": "claim_claimable_balance", "balanceId": "A" * 64},
            # Неизвестный тип сборщик игнорирует - поведение сохранено.
            {"type": "some_unknown_type", "whatever": {"nested": True}},
        ],
        id="data-pool-balance-unknown",
    ),
    pytest.param(
        [
            # float2str() принимает запятую как десятичный разделитель.
            {
                "type": "payment",
                "destination": OTHER_ACCOUNT,
                "asset": "XLM",
                "amount": "1,5",
            },
            # threshold "" и отсутствующие/null master/home - необязательные поля.
            {"type": "set_options", "threshold": ""},
            {"type": "set_options", "threshold": 2},
            {"type": "set_options", "threshold": "1", "master": None, "home": ""},
            {
                "type": "create_claimable_balance",
                "asset": "XLM",
                "amount": "1",
                "claimant_1_destination": OTHER_ACCOUNT,
                "claimant_1_predicate_type": "abs_before",
                "claimant_1_predicate_value": "2026-03-07T18:00:00Z",
            },
            {
                "type": "create_claimable_balance",
                "asset": "XLM",
                "amount": "1",
                "claimant_1_destination": OTHER_ACCOUNT,
                "claimant_1_predicate_type": "rel_before",
                "claimant_1_predicate_value": "3600",
            },
        ],
        id="optional-fields-and-predicates",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("operations", VALID_BUILD_XDR_OPERATIONS)
async def test_lab_build_xdr_accepts_valid_payloads(client, operations):
    """Корректные payload'ы по-прежнему доходят до сборщика XDR без изменений."""
    payload = {"publicKey": ACCOUNT, "sequence": "0", "operations": operations}
    build_mock = AsyncMock(return_value="AAAA")
    with patch("routers.laboratory.stellar_build_xdr", new=build_mock):
        response = await client.post("/lab/build_xdr", json=payload)

    assert response.status_code == 200
    assert await response.get_json() == {"xdr": "AAAA"}
    build_mock.assert_awaited_once_with(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_body",
    [
        '{"publicKey": "GABC", "sequence": 1e999, "operations": []}',
        '{"publicKey": "GABC", "operations": [{"type": "bump_sequence", "bump_to": 1e999}]}',
    ],
    ids=["sequence-overflow", "bump-to-overflow"],
)
async def test_lab_build_xdr_rejects_numeric_overflow(client, raw_body):
    """1e999 парсится в infinity: int(inf) -> OverflowError, ожидаем 400, не 500."""
    build_mock = AsyncMock(return_value="AAAA")
    with patch("routers.laboratory.stellar_build_xdr", new=build_mock):
        response = await client.post(
            "/lab/build_xdr",
            data=raw_body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    assert "must be an integer" in (await response.get_json())["error"]
    build_mock.assert_not_awaited()


PAY_DIVS_OVERFLOW_BODY = (
    '{"publicKey": "GABC", "operations": [{"type": "pay_divs", '
    '"holders": "XLM", "asset": "XLM", "amount": "1", "__FIELD__": 1e999}]}'
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field_name",
    ["require_trustline", "requireTrustline"],
    ids=["require_trustline", "requireTrustline-alias"],
)
async def test_lab_build_xdr_rejects_pay_divs_flag_overflow(client, field_name):
    """pay_divs: int(inf) в сборщике -> OverflowError; на границе — 400.

    Сборщик ловит только TypeError/ValueError, поэтому переполнение
    require_trustline / requireTrustline раньше давало HTTP 500.
    """
    raw_body = PAY_DIVS_OVERFLOW_BODY.replace("__FIELD__", field_name)
    build_mock = AsyncMock(return_value="AAAA")
    with patch("routers.laboratory.stellar_build_xdr", new=build_mock):
        response = await client.post(
            "/lab/build_xdr",
            data=raw_body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    error = (await response.get_json())["error"]
    assert f"operations[0].{field_name}" in error
    assert "out of range" in error
    build_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_lab_build_xdr_accepts_shadowed_pay_divs_alias_overflow(client):
    """Затенённый алиас (require_trustline задан) сборщик не читает — 200 сохранён."""
    raw_body = (
        '{"publicKey": "GABC", "operations": [{"type": "pay_divs", '
        '"holders": "XLM", "asset": "XLM", "amount": "1", '
        '"require_trustline": null, "requireTrustline": 1e999}]}'
    )
    build_mock = AsyncMock(return_value="AAAA")
    with patch("routers.laboratory.stellar_build_xdr", new=build_mock):
        response = await client.post(
            "/lab/build_xdr",
            data=raw_body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert await response.get_json() == {"xdr": "AAAA"}
    build_mock.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flag_payload",
    [
        {"require_trustline": "1"},
        {"require_trustline": "0"},
        {"require_trustline": 1},
        {"require_trustline": 0},
        {"require_trustline": "abc"},
        {"require_trustline": None},
        {"requireTrustline": "0"},
        {"requireTrustline": 1},
        {},
    ],
    ids=[
        "str-1",
        "str-0",
        "int-1",
        "int-0",
        "garbage-string-fallback",
        "null",
        "alias-str-0",
        "alias-int-1",
        "absent",
    ],
)
async def test_lab_build_xdr_accepts_pay_divs_flag_variants(client, flag_payload):
    """Допустимые значения require_trustline/алиаса не отклоняются."""
    operation = {
        "type": "pay_divs",
        "holders": ASSET,
        "asset": "XLM",
        "amount": "1",
        **flag_payload,
    }
    payload = {"publicKey": ACCOUNT, "operations": [operation]}
    build_mock = AsyncMock(return_value="AAAA")
    with patch("routers.laboratory.stellar_build_xdr", new=build_mock):
        response = await client.post("/lab/build_xdr", json=payload)

    assert response.status_code == 200
    assert await response.get_json() == {"xdr": "AAAA"}
    build_mock.assert_awaited_once_with(payload)


@pytest.mark.asyncio
async def test_lab_build_xdr_builds_real_pay_divs_xdr(client):
    """Реальная сборка pay_divs: флаг и алиас доходят до сборщика как раньше."""
    root_key = Keypair.random().public_key
    holder = Keypair.random().public_key
    pay_divs_mock = AsyncMock(return_value=[{"account": holder, "payment": 2.5}])

    with (
        patch("stellar_sdk.Server.load_account", return_value=Account(root_key, 1)),
        patch("services.stellar_client.pay_divs", new=pay_divs_mock),
    ):
        response = await client.post(
            "/lab/build_xdr",
            json={
                "publicKey": root_key,
                "sequence": "11",
                "operations": [
                    {
                        "type": "pay_divs",
                        "holders": "XLM",
                        "asset": "XLM",
                        "amount": "5",
                        "requireTrustline": "0",
                    }
                ],
            },
        )

    assert response.status_code == 200
    xdr = (await response.get_json())["xdr"]
    transaction = TransactionEnvelope.from_xdr(
        xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction

    assert isinstance(transaction.operations[0], Payment)
    assert transaction.operations[0].amount == "2.5"
    assert pay_divs_mock.await_args.kwargs["require_trustline"] is False


@pytest.mark.asyncio
async def test_lab_build_xdr_builds_real_payment_xdr(client):
    """Реальная сборка (Horizon замокан): корректный payment даёт валидный XDR."""
    root_key = Keypair.random().public_key
    destination = Keypair.random().public_key

    with patch("stellar_sdk.Server.load_account", return_value=Account(root_key, 1)):
        response = await client.post(
            "/lab/build_xdr",
            json={
                "publicKey": root_key,
                "sequence": "42",
                "operations": [
                    {
                        "type": "payment",
                        "destination": destination,
                        "asset": "XLM",
                        "amount": "10.5",
                    }
                ],
            },
        )

    assert response.status_code == 200
    xdr = (await response.get_json())["xdr"]
    transaction = TransactionEnvelope.from_xdr(
        xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction

    assert transaction.sequence == 42
    assert isinstance(transaction.operations[0], Payment)
    assert transaction.operations[0].amount == "10.5"


@pytest.mark.asyncio
async def test_lab_build_xdr_builds_real_withdraw_xdr_with_comma_amount(client):
    """amount="1,5" корректен при ненулевых минимумах: float2str, без share_ratio."""
    root_key = Keypair.random().public_key
    pool_data_mock = AsyncMock()

    with (
        patch("stellar_sdk.Server.load_account", return_value=Account(root_key, 1)),
        patch("services.stellar_client.get_pool_data", new=pool_data_mock),
    ):
        response = await client.post(
            "/lab/build_xdr",
            json={
                "publicKey": root_key,
                "sequence": "5",
                "operations": [
                    {
                        "type": "liquidity_pool_withdraw",
                        "liquidity_pool_id": "a" * 64,
                        "amount": "1,5",
                        "min_amount_a": "1",
                        "min_amount_b": "1",
                    }
                ],
            },
        )

    assert response.status_code == 200
    xdr = (await response.get_json())["xdr"]
    operation = TransactionEnvelope.from_xdr(
        xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction.operations[0]

    assert isinstance(operation, LiquidityPoolWithdraw)
    assert operation.amount == "1.5"
    pool_data_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_lab_build_xdr_builds_real_swap_xdr(client):
    """swap с asset_type в path.passes валидацию и реально собирается в XDR."""
    root_key = Keypair.random().public_key
    issuer = Keypair.random().public_key

    with patch("stellar_sdk.Server.load_account", return_value=Account(root_key, 1)):
        response = await client.post(
            "/lab/build_xdr",
            json={
                "publicKey": root_key,
                "sequence": "7",
                "operations": [
                    {
                        "type": "swap",
                        "selling": "XLM",
                        "buying": f"USD-{issuer}",
                        "amount": "1",
                        "destination": "0.5",
                        "path": (
                            '[{"asset_type": "native"}, '
                            '{"asset_type": "credit_alphanum4", '
                            f'"asset_code": "EUR", "asset_issuer": "{issuer}"}}]'
                        ),
                    }
                ],
            },
        )

    assert response.status_code == 200
    xdr = (await response.get_json())["xdr"]
    operation = TransactionEnvelope.from_xdr(
        xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    ).transaction.operations[0]

    assert isinstance(operation, PathPaymentStrictSend)
    assert [asset.code for asset in operation.path] == ["XLM", "EUR"]
    assert operation.dest_min == "0.5"


@pytest.mark.asyncio
async def test_lab_xdr_to_json_returns_decoded_payload(client):
    with patch(
        "routers.laboratory.decode_xdr_to_base64",
        return_value={"ok": True, "operations": []},
    ) as decode_mock:
        response = await client.post("/lab/xdr_to_json", json={"xdr": "AAAA"})

    assert response.status_code == 200
    assert await response.get_json() == {"ok": True, "operations": []}
    decode_mock.assert_called_once_with("AAAA", return_json=True)


@pytest.mark.asyncio
async def test_lab_xdr_to_json_rejects_invalid_xdr(client):
    with patch(
        "routers.laboratory.decode_xdr_to_base64",
        side_effect=ValueError("Invalid Stellar XDR"),
    ):
        response = await client.post("/lab/xdr_to_json", json={"xdr": "AAAA"})

    assert response.status_code == 400
    assert await response.get_json() == {"error": "Invalid Stellar XDR"}


@pytest.mark.asyncio
async def test_lab_update_memo_rejects_invalid_xdr(client):
    response = await client.post("/lab/update_memo", json={"xdr": "", "memo": "memo"})

    assert response.status_code == 400
    assert await response.get_json() == {"error": "Invalid or missing XDR"}


@pytest.mark.asyncio
async def test_lab_update_memo_rejects_invalid_memo_length(client):
    response = await client.post("/lab/update_memo", json={"xdr": "AAAA", "memo": "ab"})

    assert response.status_code == 400
    assert await response.get_json() == {
        "error": "Invalid memo length. Must be between 3 characters and 28 bytes"
    }


@pytest.mark.asyncio
async def test_lab_update_memo_rejects_memo_over_28_bytes(client):
    response = await client.post(
        "/lab/update_memo",
        json={"xdr": "AAAA", "memo": "абвгдежзийклмнопр"},
    )

    assert response.status_code == 400
    assert await response.get_json() == {
        "error": "Invalid memo length. Must be between 3 characters and 28 bytes"
    }


@pytest.mark.asyncio
async def test_lab_update_memo_rejects_control_characters(client):
    response = await client.post(
        "/lab/update_memo",
        json={"xdr": "AAAA", "memo": "bad\nmemo"},
    )

    assert response.status_code == 400
    assert await response.get_json() == {
        "error": "Memo must contain only printable characters"
    }


@pytest.mark.asyncio
async def test_lab_update_memo_returns_updated_xdr(client):
    with patch(
        "routers.laboratory.update_memo_in_xdr", return_value="BBBB"
    ) as update_mock:
        response = await client.post(
            "/lab/update_memo",
            json={"xdr": "AAAA", "memo": "valid memo"},
        )

    assert response.status_code == 200
    assert await response.get_json() == {"success": True, "xdr": "BBBB"}
    update_mock.assert_called_once_with("AAAA", "valid memo")


@pytest.mark.asyncio
async def test_lab_update_memo_accepts_cyrillic_spaces_and_punctuation(client):
    with patch(
        "routers.laboratory.update_memo_in_xdr", return_value="BBBB"
    ) as update_mock:
        response = await client.post(
            "/lab/update_memo",
            json={"xdr": "AAAA", "memo": "Привет, MTL!"},
        )

    assert response.status_code == 200
    assert await response.get_json() == {"success": True, "xdr": "BBBB"}
    update_mock.assert_called_once_with("AAAA", "Привет, MTL!")
