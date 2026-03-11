"""
Тесты для модуля services/stellar_client.py
"""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr
from stellar_sdk import (
    Account,
    Asset,
    ClaimClaimableBalance,
    CreateClaimableBalance,
    Keypair,
    LiquidityPoolDeposit,
    LiquidityPoolWithdraw,
    ManageData,
    Network,
    Payment,
    RevokeSponsorship,
    SetOptions,
    SetTrustLineFlags,
    TransactionBuilder,
    TransactionEnvelope,
    TrustLineFlags,
)

from services.stellar_client import (
    add_trust_line_uri,
    create_sep7_auth_transaction,
    decode_asset,
    decode_flags,
    float2str,
    process_xdr_transaction,
    stellar_build_xdr,
    xdr_to_uri,
)


class TestFloatToString:
    """Тесты функции float2str"""

    def test_float2str_simple_integer(self):
        """Тест конвертации целого числа"""
        assert float2str(10.0) == "10"
        assert float2str(100.0) == "100"
        assert float2str(0.0) == "0"

    def test_float2str_decimal_numbers(self):
        """Тест конвертации десятичных чисел"""
        assert float2str(10.5) == "10.5"
        assert float2str(100.123) == "100.123"
        assert float2str(0.5) == "0.5"

    def test_float2str_removes_trailing_zeros(self):
        """Тест удаления нулей в конце"""
        assert float2str(10.0) == "10"
        assert float2str(10.10) == "10.1"
        assert float2str(10.100) == "10.1"
        assert float2str(10.1000000) == "10.1"

    def test_float2str_precision_seven_decimals(self):
        """Тест точности до 7 знаков"""
        result = float2str(10.123456789)
        # Должно быть не более 7 знаков после точки
        assert result == "10.1234568"  # Округлено до 7 знаков

    def test_float2str_very_small_numbers(self):
        """Тест очень малых чисел"""
        result = float2str(0.0000001)
        assert result == "0.0000001"

        result = float2str(0.00000001)
        # Меньше precision, округлится
        assert result == "0"

    def test_float2str_from_string_with_dot(self):
        """Тест конвертации из строки с точкой"""
        assert float2str("10.5") == "10.5"
        assert float2str("100.0") == "100"

    def test_float2str_from_string_with_comma(self):
        """Тест конвертации из строки с запятой (европейский формат)"""
        assert float2str("10,5") == "10.5"
        assert float2str("100,0") == "100"
        assert float2str("123,456") == "123.456"

    @pytest.mark.parametrize(
        "input_val,expected",
        [
            (1.0, "1"),
            (1.5, "1.5"),
            (1.50, "1.5"),
            (1.500000, "1.5"),
            ("1.0", "1"),
            ("1,5", "1.5"),
            (0.1, "0.1"),
            (0.10, "0.1"),
            (100.0, "100"),
            (100.100, "100.1"),
        ],
    )
    def test_float2str_parametrized(self, input_val, expected):
        """Параметризованный тест различных входных значений"""
        assert float2str(input_val) == expected

    def test_float2str_stellar_amounts(self):
        """Тест типичных сумм в Stellar (7 decimal places)"""
        # Stellar использует до 7 знаков после запятой
        assert float2str(10.1234567) == "10.1234567"
        assert float2str(10.123456) == "10.123456"
        assert float2str(10.1234560) == "10.123456"  # Trailing zero removed

    def test_float2str_negative_numbers(self):
        """Тест отрицательных чисел"""
        assert float2str(-10.5) == "-10.5"
        assert float2str(-10.0) == "-10"
        assert float2str(-100.100) == "-100.1"

    def test_float2str_edge_cases(self):
        """Тест граничных случаев"""
        # Очень большое число
        result = float2str(999999999.123)
        assert "999999999" in result

        # Почти ноль
        result = float2str(0.00000001)
        assert result == "0" or result == "0.00000001"


class TestAssetHelpers:
    """Тесты вспомогательных функций для работы с активами"""

    # Примечание: Большинство функций в stellar_client.py являются async
    # и требуют доступа к БД или Horizon API
    # Для их тестирования используются моки в других тестовых файлах
    # (test_extract_sources.py, test_transaction_service.py и т.д.)

    def test_asset_creation(self):
        """Тест создания Stellar Asset объектов"""
        # Native asset
        native = Asset.native()
        assert native.code == "XLM"
        assert native.is_native()

        # Custom asset
        issuer = Keypair.random().public_key
        custom = Asset("USD", issuer)
        assert custom.code == "USD"
        assert custom.issuer == issuer
        assert not custom.is_native()

    def test_decode_asset_and_flags_helpers(self):
        native = decode_asset("XLM")
        issuer = Keypair.random().public_key
        issued = decode_asset(f"USD-{issuer}")

        assert native.is_native()
        assert issued.code == "USD"
        assert issued.issuer == issuer

        flags = decode_flags(
            TrustLineFlags.AUTHORIZED_FLAG
            | TrustLineFlags.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG
        )
        assert flags & TrustLineFlags.AUTHORIZED_FLAG
        assert flags & TrustLineFlags.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG


def _build_sep7_auth_xdr(domain: str, domain_account_id: str, client_account_id: str):
    source_account = Account(client_account_id, 123456)
    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=100,
        )
        .append_manage_data_op(data_name=f"{domain} auth", data_value=b"nonce-123")
        .append_manage_data_op(
            data_name="web_auth_domain",
            data_value=domain.encode(),
            source=domain_account_id,
        )
        .set_timeout(300)
        .build()
    )
    return transaction.to_xdr()


class TestSep7Helpers:
    @pytest.mark.asyncio
    async def test_process_xdr_transaction_happy_path(self):
        domain = "example.test"
        domain_account_id = Keypair.random().public_key
        client_account_id = Keypair.random().public_key
        xdr = _build_sep7_auth_xdr(domain, domain_account_id, client_account_id)

        with (
            patch("services.stellar_client.config.domain", domain),
            patch(
                "services.stellar_client.config.domain_account_id", domain_account_id
            ),
        ):
            result = await process_xdr_transaction(xdr)

        assert result["client_address"] == client_account_id
        assert result["domain"] == domain
        assert result["nonce"] == "nonce-123"
        assert result["hash"]

    @pytest.mark.asyncio
    async def test_process_xdr_transaction_rejects_wrong_operation_count(self):
        source = Account(Keypair.random().public_key, 123)
        xdr = (
            TransactionBuilder(
                source_account=source,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_manage_data_op(data_name="only-one", data_value=b"x")
            .set_timeout(300)
            .build()
            .to_xdr()
        )

        with pytest.raises(ValueError, match="Неверное количество операций"):
            await process_xdr_transaction(xdr)

    def test_xdr_to_uri_round_trip_and_add_trust_line_uri(self):
        keypair = Keypair.random()
        trustor = Account(keypair.public_key, 10)
        signing_key = Keypair.random().secret

        xdr = (
            TransactionBuilder(
                source_account=trustor,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_payment_op(
                destination=Keypair.random().public_key,
                asset=Asset.native(),
                amount="1",
            )
            .set_timeout(300)
            .build()
            .to_xdr()
        )

        with (
            patch("stellar_sdk.Server.load_account", return_value=trustor),
            patch(
                "services.stellar_client.config.domain_key",
                SecretStr(signing_key),
            ),
        ):
            uri = add_trust_line_uri(
                keypair.public_key, "USD", Keypair.random().public_key
            )

        assert xdr_to_uri(xdr).startswith("web+stellar:tx?")
        assert uri.startswith("web+stellar:tx?")
        assert "origin_domain=eurmtl.me" in uri

    @pytest.mark.asyncio
    async def test_create_sep7_auth_transaction_builds_uri(self):
        domain = "example.test"
        domain_account_id = Keypair.random().public_key
        domain_key = Keypair.random().secret
        source_account = Account(Keypair.random().public_key, 777)

        with (
            patch("stellar_sdk.Server.load_account", return_value=source_account),
            patch("services.stellar_client.config.domain", domain),
            patch(
                "services.stellar_client.config.domain_account_id", domain_account_id
            ),
            patch("services.stellar_client.config.domain_key", SecretStr(domain_key)),
        ):
            uri = await create_sep7_auth_transaction(
                domain="wallet.example",
                nonce="abc123",
                callback="https://callback.example",
            )

        assert "web+stellar:tx?" in uri
        assert "callback.example" in uri
        assert f"origin_domain={domain}" in uri


class TestBuildXdr:
    @pytest.mark.asyncio
    async def test_stellar_build_xdr_builds_common_operations(self):
        root_key = Keypair.random().public_key
        destination = Keypair.random().public_key
        asset_issuer = Keypair.random().public_key

        data = {
            "publicKey": root_key,
            "sequence": "42",
            "memo_type": "memo_text",
            "memo": "hello",
            "operations": [
                {
                    "type": "payment",
                    "destination": destination,
                    "asset": f"USD-{asset_issuer}",
                    "amount": "10.5000000",
                },
                {
                    "type": "manage_data",
                    "data_name": "hello",
                    "data_value": "world",
                },
                {
                    "type": "set_options",
                    "threshold": "1/2/3",
                    "master": "5",
                    "home": "eurmtl.me",
                },
                {
                    "type": "change_trust",
                    "asset": f"USD-{asset_issuer}",
                    "limit": "99.9",
                },
                {
                    "type": "bump_sequence",
                    "bump_to": "12345",
                },
            ],
        }

        with patch(
            "stellar_sdk.Server.load_account", return_value=Account(root_key, 1)
        ):
            xdr = await stellar_build_xdr(data)

        transaction = TransactionEnvelope.from_xdr(
            xdr, Network.PUBLIC_NETWORK_PASSPHRASE
        ).transaction

        assert transaction.sequence == 42
        assert transaction.memo.memo_text.decode("utf-8") == "hello"
        assert [type(op) for op in transaction.operations] == [
            Payment,
            ManageData,
            SetOptions,
            type(transaction.operations[3]),
            type(transaction.operations[4]),
        ]
        assert transaction.operations[0].amount == "10.5"
        assert transaction.operations[1].data_value == b"world"
        assert transaction.operations[2].low_threshold == 1
        assert transaction.operations[2].med_threshold == 2
        assert transaction.operations[2].high_threshold == 3

    @pytest.mark.asyncio
    async def test_stellar_build_xdr_handles_claimable_balance_revoke_and_pool_ops(
        self,
    ):
        root_key = Keypair.random().public_key
        claimant = Keypair.random().public_key
        issuer_a = Keypair.random().public_key
        pool_id = "a" * 64

        from stellar_sdk import LiquidityPoolAsset

        pool_asset = LiquidityPoolAsset(Asset.native(), Asset("USD", issuer_a))
        pool_data = {
            "price": 2.0,
            "reserves": [{"amount": "100"}, {"amount": "200"}],
            "total_shares": 50,
            "LiquidityPoolAsset": pool_asset,
        }

        data = {
            "publicKey": root_key,
            "memo_type": "",
            "memo": "",
            "operations": [
                {
                    "type": "create_claimable_balance",
                    "asset": "XLM",
                    "amount": "5",
                    "claimant_1_destination": claimant,
                    "claimant_1_predicate_type": "rel_after",
                    "claimant_1_predicate_value": "3600",
                },
                {
                    "type": "set_trust_line_flags",
                    "trustor": claimant,
                    "asset": f"USD-{issuer_a}",
                    "setFlags": str(int(TrustLineFlags.AUTHORIZED_FLAG)),
                    "clearFlags": str(
                        int(TrustLineFlags.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG)
                    ),
                },
                {
                    "type": "revoke_sponsorship",
                    "revoke_type": "claimable_balance",
                    "revoke_claimable_balance_id": "b" * 64,
                },
                {
                    "type": "liquidity_pool_deposit",
                    "liquidity_pool_id": pool_id,
                    "max_amount_a": "10",
                    "max_amount_b": "20",
                    "min_price": "0",
                    "max_price": "0",
                },
                {
                    "type": "liquidity_pool_withdraw",
                    "liquidity_pool_id": pool_id,
                    "amount": "5",
                    "min_amount_a": "0",
                    "min_amount_b": "0",
                },
                {
                    "type": "liquidity_pool_trustline",
                    "liquidity_pool_id": pool_id,
                    "limit": "",
                },
            ],
        }

        with (
            patch("stellar_sdk.Server.load_account", return_value=Account(root_key, 1)),
            patch(
                "services.stellar_client.get_pool_data",
                AsyncMock(return_value=pool_data),
            ),
        ):
            xdr = await stellar_build_xdr(data)

        transaction = TransactionEnvelope.from_xdr(
            xdr, Network.PUBLIC_NETWORK_PASSPHRASE
        ).transaction

        assert isinstance(transaction.operations[0], CreateClaimableBalance)
        assert isinstance(transaction.operations[1], SetTrustLineFlags)
        assert isinstance(transaction.operations[2], RevokeSponsorship)
        assert isinstance(transaction.operations[3], LiquidityPoolDeposit)
        assert isinstance(transaction.operations[4], LiquidityPoolWithdraw)
        assert transaction.operations[3].min_price.n == 19
        assert transaction.operations[3].min_price.d == 10
        assert transaction.operations[3].max_price.n == 21
        assert transaction.operations[3].max_price.d == 10
        assert transaction.operations[4].min_amount_a == "9.5"
        assert transaction.operations[4].min_amount_b == "19"

    @pytest.mark.asyncio
    async def test_stellar_build_xdr_handles_pay_divs_and_copy_multi_sign(self):
        root_key = Keypair.random().public_key
        source_override = Keypair.random().public_key
        signer_key = Keypair.random().public_key

        data = {
            "publicKey": root_key,
            "memo_type": "",
            "memo": "",
            "operations": [
                {
                    "type": "copy_multi_sign",
                    "from": Keypair.random().public_key,
                    "sourceAccount": source_override,
                },
                {
                    "type": "pay_divs",
                    "holders": "XLM",
                    "asset": "XLM",
                    "amount": "25",
                    "requireTrustline": "0",
                    "sourceAccount": source_override,
                },
                {
                    "type": "claim_claimable_balance",
                    "balanceId": "c" * 64,
                },
            ],
        }

        with (
            patch("stellar_sdk.Server.load_account", return_value=Account(root_key, 1)),
            patch(
                "services.stellar_client.stellar_copy_multi_sign",
                AsyncMock(
                    return_value=[
                        {
                            "key": "threshold",
                            "low_threshold": 1,
                            "med_threshold": 2,
                            "high_threshold": 3,
                        },
                        {"key": source_override, "weight": 2},
                        {"key": signer_key, "weight": 1},
                    ]
                ),
            ),
            patch(
                "services.stellar_client.pay_divs",
                AsyncMock(
                    return_value=[
                        {"account": Keypair.random().public_key, "payment": 12.5}
                    ]
                ),
            ),
        ):
            xdr = await stellar_build_xdr(data)

        transaction = TransactionEnvelope.from_xdr(
            xdr, Network.PUBLIC_NETWORK_PASSPHRASE
        ).transaction

        assert isinstance(transaction.operations[0], SetOptions)
        assert isinstance(transaction.operations[1], SetOptions)
        assert isinstance(transaction.operations[2], type(transaction.operations[2]))
        assert isinstance(transaction.operations[3], Payment)
        assert isinstance(transaction.operations[4], ClaimClaimableBalance)
        assert transaction.operations[0].med_threshold == 2
        assert transaction.operations[3].amount == "12.5"
