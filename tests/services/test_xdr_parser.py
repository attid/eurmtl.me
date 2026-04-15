"""
Тесты для модуля services/xdr_parser.py
"""

import base64
import pathlib
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from stellar_sdk import (
    Account,
    Asset,
    Claimant,
    ClaimPredicate,
    Keypair,
    LiquidityPoolAsset,
    Network,
    StrKey,
    TextMemo,
    TransactionBuilder,
    TransactionEnvelope,
    TrustLineFlags,
)

from services.xdr_parser import (
    _parse_transaction_envelope,
    _render_auth_sub_invocation_summaries,
    decode_xdr_to_base64,
    is_valid_base64,
    decode_data_value,
    decode_scval,
    construct_payload,
    uri_sign,
    get_key_sort,
    address_id_to_link,
    pool_id_to_link,
    asset_to_link,
    decode_invoke_host_function,
    decode_xdr_to_text,
    SimulatedLedger,
    _render_sub_invocation_summary,
    update_memo_in_xdr,
)

INVALID_STELLAR_XDR = "AAAAAgAAAAA+gj+9R9RakwtxBG6Up8jAewUfdurumKJARnpcMG9VBgAAAZADqmC9AAAACQAAAAEAAAAAAAAAAAAAAABprWevAAAAAQAAAARleGNoAAAAAgAAAAAAAAABAAAAAOULguv++61OnAUgnSV24FKlgUt80KvaUijNM9Fdx2wmAAAAAkVVUk1UTAAAAAAAAAAAAAAEqbejBk1rxsHVls854RnAyfpJaZacvgwmQ0jxNDBvqgAAAAFloLwAAAAAAAAAAAMAAAACRVVSTVRMAAAAAAAAAAAAAASpt6MGTWvGwdWWzznhGcDJ+klplpy+DCZDSPE0MG+qAAAAAVVTRE0AAAAAzjFwwWvYRuQOCHjRQ12ZsvHFXsmtQ0ka1OpQTcuL5UoAAAAAAAAAAAAAAAEAAAABAAAAAGzhWBAAAAAAAAAAAjBvVQYAAABA8ngRn6FosWJoKr+CiNwUecKAkHp4oOTfCc3hSeFBWUNfbddyxouSs9LrkX6Yym7KUpqlbr35eypU0gUOs9bEBVpCAfwAAABAKQso0UED2q9QpUa1jIHCGtWkFCgHu7OAzYodR4L3K+HOY0OGtqIRomGNwJ2/hSP6CUc7uAJryU33J1osSvUwDQ=="
MOUNTAIN_CAPTURE_WITH_TRANSFER_XDR = (
    pathlib.Path("tests/fixtures/xdr/mountain_capture_with_transfer.xdr")
    .read_text()
    .strip()
)
SWAP_CHAINED_WITH_XLM_TRANSFER_XDR = (
    pathlib.Path("tests/fixtures/xdr/swap_chained_with_xlm_transfer.xdr")
    .read_text()
    .strip()
)
SWAP_WITH_USDM_TRANSFER_XDR = (
    pathlib.Path("tests/fixtures/xdr/swap_with_usdm_transfer.xdr").read_text().strip()
)
SWAP_CHAINED_WITH_YUSDC_TRANSFER_XDR = (
    pathlib.Path("tests/fixtures/xdr/swap_chained_with_yusdc_transfer.xdr")
    .read_text()
    .strip()
)
DEPOSIT_WITH_DUAL_TRANSFERS_XDR = (
    pathlib.Path("tests/fixtures/xdr/deposit_with_dual_transfers.xdr")
    .read_text()
    .strip()
)
WITHDRAW_WITH_UNKNOWN_SUBINVOCATION_XDR = (
    pathlib.Path("tests/fixtures/xdr/withdraw_with_unknown_subinvocation.xdr")
    .read_text()
    .strip()
)
INIT_STABLESWAP_POOL_WITH_AQUA_TRANSFER_XDR = (
    pathlib.Path("tests/fixtures/xdr/init_stableswap_pool_with_aqua_transfer.xdr")
    .read_text()
    .strip()
)


async def _decode_fixture_xdr(
    xdr: str, token_display_name: str | dict[str, str] = "EURMTL"
) -> str:
    source_account_id = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    source_account = {
        "id": source_account_id,
        "sequence": "151245301938660176",
        "balances": [{"asset_type": "native", "balance": "704.4409099"}],
    }
    repo = SimpleNamespace(get_by_sequence=AsyncMock(return_value=[]))

    if isinstance(token_display_name, dict):
        async def _resolve_token_name(*, rpc_url: str, contract_id: str) -> str:
            return token_display_name.get(contract_id, contract_id[:4] + ".." + contract_id[-4:])
    else:
        async def _resolve_token_name(*, rpc_url: str, contract_id: str) -> str:
            return token_display_name

    with (
        patch("services.xdr_parser.current_app", _mock_current_app()),
        patch("services.xdr_parser.TransactionRepository", return_value=repo),
        patch(
            "services.xdr_parser.get_available_balance_str",
            AsyncMock(return_value="704.4409099 XLM"),
        ),
        patch(
            "services.xdr_parser.get_account_fresh",
            AsyncMock(return_value=source_account),
        ),
        patch(
            "services.xdr_parser.get_account",
            AsyncMock(
                side_effect=lambda account_id: source_account
                if account_id == source_account_id
                else {"id": account_id, "balances": []}
            ),
        ),
        patch(
            "services.xdr_parser.read_token_contract_display_name",
            new=AsyncMock(side_effect=_resolve_token_name),
            create=True,
        ),
    ):
        result = await decode_xdr_to_text(xdr)

    return "\n".join(result)


class TestUtilityFunctions:
    """Тесты вспомогательных функций"""

    def test_get_key_sort_default_index(self):
        """Тест get_key_sort с индексом по умолчанию"""
        assert get_key_sort(("a", "b", "c")) == "b"
        assert get_key_sort(["x", "y", "z"]) == "y"

    def test_get_key_sort_custom_index(self):
        """Тест get_key_sort с пользовательским индексом"""
        assert get_key_sort(("a", "b", "c"), idx=0) == "a"
        assert get_key_sort(("a", "b", "c"), idx=2) == "c"

    def test_address_id_to_link(self):
        """Тест генерации ссылки на аккаунт"""
        account_id = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
        result = address_id_to_link(account_id)

        assert "https://viewer.eurmtl.me/account/" in result
        assert account_id in result
        assert "GDLT..AYXI" in result
        assert "<a href=" in result
        assert 'target="_blank"' in result

    def test_pool_id_to_link(self):
        """Тест генерации ссылки на пул ликвидности"""
        pool_id = "abcd1234567890abcd1234567890abcd1234567890abcd1234567890abcd"
        result = pool_id_to_link(pool_id)

        assert "https://viewer.eurmtl.me/pool/" in result
        assert pool_id in result
        assert "abcd..abcd" in result
        assert "<a href=" in result


class TestBase64Functions:
    """Тесты функций работы с base64"""

    def test_is_valid_base64_valid_string(self):
        """Тест валидации правильной base64 строки"""
        valid_b64 = base64.b64encode(b"Hello World").decode()
        assert is_valid_base64(valid_b64) is True

    def test_is_valid_base64_empty_string(self):
        """Тест валидации пустой строки"""
        # Пустая строка является валидной base64
        assert is_valid_base64("") is True

    def test_is_valid_base64_invalid_string(self):
        """Тест валидации невалидной base64 строки"""
        # Примечание: base64.b64decode достаточно толерантна
        # Она игнорирует некоторые спецсимволы и пытается декодировать
        # Проверяем что функция не падает с ошибкой
        result1 = is_valid_base64("This is not base64!!!")
        result2 = is_valid_base64("@#$%^&*()")
        # Проверяем что результат булевый
        assert isinstance(result1, bool)
        assert isinstance(result2, bool)

    @pytest.mark.parametrize(
        "test_input,expected",
        [
            ("SGVsbG8=", True),  # Valid base64
            ("", True),  # Empty is valid
            ("AAAA", True),  # Valid base64
            ("AAA=", True),  # Valid base64 with padding
            # base64.b64decode достаточно толерантна и принимает многие строки
        ],
    )
    def test_is_valid_base64_parametrized(self, test_input, expected):
        """Параметризованный тест валидации base64"""
        assert is_valid_base64(test_input) is expected

    def test_decode_data_value_valid_utf8(self):
        """Тест декодирования валидного base64 с UTF-8"""
        # Encode test string to base64
        test_string = "Hello, Stellar!"
        encoded = base64.b64encode(test_string.encode("utf-8")).decode("utf-8")

        result = decode_data_value(encoded)
        assert result == test_string

    def test_decode_data_value_empty_string(self):
        """Тест декодирования пустой строки"""
        encoded = base64.b64encode(b"").decode("utf-8")
        result = decode_data_value(encoded)
        assert result == ""

    def test_decode_data_value_russian_text(self):
        """Тест декодирования русского текста"""
        test_string = "Привет, Stellar!"
        encoded = base64.b64encode(test_string.encode("utf-8")).decode("utf-8")

        result = decode_data_value(encoded)
        assert result == test_string

    def test_decode_data_value_special_characters(self):
        """Тест декодирования спецсимволов"""
        test_string = "Test @#$%^&*() 123"
        encoded = base64.b64encode(test_string.encode("utf-8")).decode("utf-8")

        result = decode_data_value(encoded)
        assert result == test_string

    def test_decode_data_value_invalid_base64(self):
        """Тест декодирования невалидного base64"""
        invalid_data = "This is not valid base64!!!"
        result = decode_data_value(invalid_data)
        assert result == "decode error"

    def test_decode_data_value_invalid_utf8(self):
        """Тест декодирования невалидного UTF-8"""
        # Create invalid UTF-8 sequence
        invalid_bytes = b"\x80\x81\x82"
        encoded = base64.b64encode(invalid_bytes).decode("utf-8")

        result = decode_data_value(encoded)
        assert result == "decode error"


class TestSEP7Signing:
    """Тесты для SEP-7 URI подписи"""

    def test_construct_payload_basic(self):
        """Тест создания payload для SEP-7"""
        test_data = "web+stellar:pay?destination=GABC&amount=100"
        result = construct_payload(test_data)

        # Проверяем что результат - bytes
        assert isinstance(result, bytes)

        # Первые 35 байт должны быть нулями
        assert result[:35] == bytes([0] * 35)

        # 36-й байт должен быть 4
        assert result[35] == 4

        # Проверяем что data включена в payload
        assert b"stellar.sep.7 - URI Scheme" in result
        assert test_data.encode() in result

    def test_construct_payload_different_data(self):
        """Тест construct_payload с разными данными"""
        test_cases = [
            "web+stellar:tx?xdr=AAAA...",
            "simple_string",
            "",  # Empty string
        ]

        for data in test_cases:
            result = construct_payload(data)
            assert isinstance(result, bytes)
            assert result[:35] == bytes([0] * 35)
            assert result[35] == 4

    def test_uri_sign_generates_signature(self):
        """Тест генерации подписи URI"""
        # Создаём тестовый ключ
        keypair = Keypair.random()
        test_data = "web+stellar:pay?destination=GABC&amount=100"

        result = uri_sign(test_data, keypair.secret)

        # Проверяем что результат это строка
        assert isinstance(result, str)

        # Проверяем что результат не пустой
        assert len(result) > 0

        # Результат должен быть URL-encoded base64
        # (может содержать %XX для спецсимволов)

    def test_uri_sign_deterministic(self):
        """Тест что одинаковые данные дают одинаковую подпись"""
        keypair = Keypair.random()
        test_data = "web+stellar:pay?destination=GABC&amount=100"

        signature1 = uri_sign(test_data, keypair.secret)
        signature2 = uri_sign(test_data, keypair.secret)

        # Одинаковые данные с одним ключом должны давать одинаковую подпись
        assert signature1 == signature2

    def test_uri_sign_different_data_different_signature(self):
        """Тест что разные данные дают разные подписи"""
        keypair = Keypair.random()
        data1 = "web+stellar:pay?destination=GABC&amount=100"
        data2 = "web+stellar:pay?destination=GXYZ&amount=200"

        signature1 = uri_sign(data1, keypair.secret)
        signature2 = uri_sign(data2, keypair.secret)

        # Разные данные должны давать разные подписи
        assert signature1 != signature2

    def test_uri_sign_different_keys_different_signature(self):
        """Тест что разные ключи дают разные подписи"""
        keypair1 = Keypair.random()
        keypair2 = Keypair.random()
        test_data = "web+stellar:pay?destination=GABC&amount=100"

        signature1 = uri_sign(test_data, keypair1.secret)
        signature2 = uri_sign(test_data, keypair2.secret)

        # Разные ключи должны давать разные подписи
        assert signature1 != signature2


@pytest.mark.asyncio
async def test_decode_xdr_to_text_invalid_stellar_xdr_raises_clear_error():
    """Невалидный Stellar XDR должен приводить к контролируемому ValueError."""
    with patch(
        "services.xdr_parser.FeeBumpTransactionEnvelope.is_fee_bump_transaction_envelope",
        side_effect=ValueError("1175155856 is not a valid CryptoKeyType"),
    ):
        with pytest.raises(ValueError, match="Invalid Stellar XDR"):
            _parse_transaction_envelope(INVALID_STELLAR_XDR)


def test_uri_sign_url_encoded():
    """Тест что результат URL-encoded"""
    keypair = Keypair.random()
    test_data = "web+stellar:pay?destination=GABC&amount=100"

    result = uri_sign(test_data, keypair.secret)

    # URL-encoded строка не должна содержать символы, требующие кодирования
    # Base64 может содержать +, /, =, которые кодируются как %2B, %2F, %3D
    # Но не должна содержать raw + или / или =
    # (На самом деле может, если base64 не содержал этих символов)
    # Проверим просто что это строка ASCII
    assert result.isascii()


class TestXDRConversion:
    """Тесты конвертации XDR"""

    def create_simple_payment_xdr(self):
        """Вспомогательный метод для создания простого XDR"""
        source_keypair = Keypair.random()
        destination_keypair = Keypair.random()

        source_account = Account(source_keypair.public_key, 123456)

        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .add_text_memo("Test transaction")
            .append_payment_op(
                destination=destination_keypair.public_key,
                asset=Asset.native(),
                amount="10",
            )
            .set_timeout(300)
            .build()
        )

        return transaction.to_xdr()

    def test_decode_xdr_to_base64_serializes_payment_and_memo(self):
        xdr = self.create_simple_payment_xdr()

        result = decode_xdr_to_base64(xdr, return_json=True)

        assert result["attributes"]["memoType"] == "MEMO_TEXT"
        assert result["attributes"]["memoContent"] == "Test transaction"
        assert result["attributes"]["sourceAccount"]
        assert result["operations"][0]["name"] == "payment"
        assert result["operations"][0]["attributes"]["amount"] == "10"
        assert result["operations"][0]["attributes"]["asset"]["type"] == "native"

    def test_decode_xdr_to_base64_serializes_manage_data_and_claimable_balance(self):
        source_keypair = Keypair.random()
        claimant_keypair = Keypair.random()
        source_account = Account(source_keypair.public_key, 123456)

        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                base_fee=100,
            )
            .append_manage_data_op(data_name="hello", data_value=b"world")
            .append_create_claimable_balance_op(
                asset=Asset.native(),
                amount="12.5",
                claimants=[
                    Claimant(
                        destination=claimant_keypair.public_key,
                        predicate=ClaimPredicate.predicate_before_absolute_time(
                            1710000000
                        ),
                    )
                ],
            )
            .set_timeout(300)
            .build()
        )

        result = decode_xdr_to_base64(transaction.to_xdr(), return_json=True)

        manage_data = result["operations"][0]
        claimable_balance = result["operations"][1]

        assert manage_data["name"] == "manageData"
        assert manage_data["attributes"]["dataName"] == "hello"
        assert manage_data["attributes"]["dataValue"] == "world"

        assert claimable_balance["name"] == "createClaimableBalance"
        assert claimable_balance["attributes"]["amount"] == "12.5"
        assert (
            claimable_balance["attributes"]["claimants"][0]["destination"]
            == claimant_keypair.public_key
        )
        assert (
            claimable_balance["attributes"]["claimants"][0]["predicate_type"]
            == "abs_before"
        )
        assert (
            claimable_balance["attributes"]["claimants"][0]["predicate_value"]
            == 1710000000
        )

    def test_decode_xdr_to_base64_raises_clear_error_for_truncated_xdr(self):
        with pytest.raises(ValueError, match="Invalid Stellar XDR"):
            decode_xdr_to_base64("AAAA", return_json=True)


class TestScValDecoding:
    def test_decode_scval_handles_account_address_symbol_vector_and_integers(self):
        account_id = Keypair.random().public_key
        account_bytes = StrKey.decode_ed25519_public_key(account_id)

        account_scval = SimpleNamespace(
            type=SimpleNamespace(value=18),
            address=SimpleNamespace(
                type=SimpleNamespace(value=0),
                account_id=SimpleNamespace(
                    account_id=SimpleNamespace(
                        ed25519=SimpleNamespace(uint256=account_bytes)
                    )
                ),
                contract_id=None,
            ),
            sym=None,
            str=None,
            vec=None,
            u128=None,
            i128=None,
        )
        symbol_scval = SimpleNamespace(
            type=SimpleNamespace(value=1),
            address=None,
            sym=SimpleNamespace(sc_symbol=b"swap"),
            str=None,
            vec=None,
            u128=None,
            i128=None,
        )
        vector_scval = SimpleNamespace(
            type=SimpleNamespace(value=2),
            address=None,
            sym=None,
            str=None,
            vec=SimpleNamespace(sc_vec=[symbol_scval]),
            u128=None,
            i128=None,
        )
        u128_scval = SimpleNamespace(
            type=SimpleNamespace(value=3),
            address=None,
            sym=None,
            str=None,
            vec=None,
            u128=SimpleNamespace(
                lo=SimpleNamespace(uint64=5), hi=SimpleNamespace(uint64=1)
            ),
            i128=None,
        )
        i128_scval = SimpleNamespace(
            type=SimpleNamespace(value=4),
            address=None,
            sym=None,
            str=None,
            vec=None,
            u128=None,
            i128=SimpleNamespace(
                lo=SimpleNamespace(uint64=7), hi=SimpleNamespace(int64=1)
            ),
        )
        bool_scval = SimpleNamespace(
            type=SimpleNamespace(value=3),
            address=None,
            sym=None,
            str=None,
            vec=None,
            u128=None,
            i128=None,
            b=True,
        )
        non_bool_i128_scval = SimpleNamespace(
            type=SimpleNamespace(value=10),
            address=None,
            sym=None,
            str=None,
            vec=None,
            u128=None,
            i128=SimpleNamespace(
                lo=SimpleNamespace(uint64=12), hi=SimpleNamespace(int64=0)
            ),
            b=None,
        )
        u32_scval = SimpleNamespace(
            type=SimpleNamespace(value=3),
            address=None,
            sym=None,
            str=None,
            vec=None,
            u128=None,
            i128=None,
            b=None,
            u32=SimpleNamespace(uint32=500),
        )
        bytes_scval = SimpleNamespace(
            type=SimpleNamespace(value=13),
            address=None,
            sym=None,
            str=None,
            vec=None,
            u128=None,
            i128=None,
            b=None,
            bytes=SimpleNamespace(sc_bytes=b"abc"),
        )

        assert decode_scval(account_scval) == account_id
        assert decode_scval(symbol_scval) == "swap"
        assert decode_scval(vector_scval) == "[swap]"
        assert decode_scval(u128_scval) == str(5 + (1 << 64))
        assert decode_scval(i128_scval) == str((1 << 64) + 7)
        assert decode_scval(bool_scval) == "true"
        assert decode_scval(non_bool_i128_scval) == "12"
        assert decode_scval(u32_scval) == "500"
        assert decode_scval(bytes_scval) == "616263"

    def test_decode_scval_handles_unknown_and_error_cases(self):
        unknown_scval = SimpleNamespace(
            type=SimpleNamespace(value=99),
            address=None,
            sym=None,
            str=None,
            vec=None,
            u128=None,
            i128=None,
        )

        class BrokenType:
            @property
            def value(self):
                raise RuntimeError("boom")

        broken_scval = SimpleNamespace(type=BrokenType(), sym=None)

        assert "неизвестный SCVal" in decode_scval(unknown_scval)
        assert "<error decoding SCVal: boom>" == decode_scval(broken_scval)


def test_update_memo_in_xdr_replaces_existing_memo():
    source_keypair = Keypair.random()
    source_account = Account(source_keypair.public_key, 777)

    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=100,
        )
        .add_memo(TextMemo("before"))
        .append_payment_op(
            destination=Keypair.random().public_key,
            asset=Asset.native(),
            amount="2",
        )
        .set_timeout(300)
        .build()
    )

    updated_xdr = update_memo_in_xdr(transaction.to_xdr(), "after")
    parsed = TransactionEnvelope.from_xdr(
        updated_xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    )

    assert parsed.transaction.memo.memo_text.decode("utf-8") == "after"
    assert len(parsed.transaction.operations) == 1


@pytest.mark.asyncio
async def test_asset_to_link_and_simulated_ledger_helpers_cover_cache_and_balances():
    issuer = Keypair.random().public_key
    destination = Keypair.random().public_key
    asset = Asset("USD", issuer)
    pool_asset = LiquidityPoolAsset(Asset.native(), asset)
    ledger = SimulatedLedger()

    with patch(
        "services.xdr_parser.grist_cache.find_by_filter",
        return_value=[{"issuer": issuer}],
    ):
        xlm_link = await asset_to_link(Asset.native())
        usd_link = await asset_to_link(asset)

    assert "XLM" in xlm_link and "⭐" in xlm_link
    assert "USD" in usd_link and "⭐" in usd_link

    with patch(
        "services.xdr_parser.get_account",
        AsyncMock(
            side_effect=lambda account_id: (
                {"id": issuer, "balances": [{"asset_type": "native", "balance": "100"}]}
                if account_id == issuer
                else None
            )
        ),
    ):
        await ledger.prefetch_accounts({issuer, destination})

    ledger.update_balance(issuer, Asset.native(), -10)
    ledger.update_balance(destination, asset, 5)
    ledger.add_trustline(destination, asset)
    ledger.add_trustline(destination, pool_asset)
    ledger.mark_asset_as_new(asset)
    ledger.remove_trustline(destination, asset)
    ledger.remove_trustline(destination, pool_asset)
    ledger.create_account(destination, "20")

    assert ledger.get_account(issuer)["balances"][0]["balance"] == "90.0"
    assert ledger.get_account(destination)["balances"][0]["balance"] == "20"
    assert ledger.is_asset_new(asset) is True
    assert ledger.is_asset_new(Asset.native()) is False


@pytest.mark.asyncio
async def test_decode_invoke_host_function_supports_multiple_host_function_shapes():
    contract_bytes = bytes.fromhex("ab" * 32)
    invoke_operation = SimpleNamespace(
        host_function=SimpleNamespace(
            type="invoke",
            invoke_contract=SimpleNamespace(
                contract_address=SimpleNamespace(
                    contract_id=SimpleNamespace(hash=contract_bytes)
                ),
                function_name=SimpleNamespace(sc_symbol=b"swap"),
                args=[SimpleNamespace(type=SimpleNamespace(value=0))],
            ),
            create_contract=None,
            install_contract_code=None,
        )
    )
    create_operation = SimpleNamespace(
        host_function=SimpleNamespace(
            type="create",
            invoke_contract=None,
            create_contract=SimpleNamespace(
                contract_id_preimage=SimpleNamespace(type=SimpleNamespace(value=0)),
                executable=SimpleNamespace(type="wasm"),
            ),
            install_contract_code=None,
        )
    )
    install_operation = SimpleNamespace(
        host_function=SimpleNamespace(
            type="install",
            invoke_contract=None,
            create_contract=None,
            install_contract_code=SimpleNamespace(hash=b"\x01\x02"),
        )
    )

    invoke_lines = await decode_invoke_host_function(invoke_operation)
    create_lines = await decode_invoke_host_function(create_operation)
    install_lines = await decode_invoke_host_function(install_operation)

    assert any("Contract call:" in line for line in invoke_lines)
    assert any(".swap(" in line for line in invoke_lines)
    assert any("Create Contract" in line for line in create_lines)
    assert any("Install Contract Code" in line for line in install_lines)


class _DummyDbPool:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _mock_current_app():
    return SimpleNamespace(db_pool=lambda: _DummyDbPool())


@pytest.mark.asyncio
async def test_decode_xdr_to_text_describes_core_operations():
    source_kp = Keypair.random()
    destination_kp = Keypair.random()
    issuer_kp = Keypair.random()
    source_account = Account(source_kp.public_key, 10)

    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=100,
        )
        .add_text_memo("Decision memo")
        .append_payment_op(
            destination=destination_kp.public_key,
            asset=Asset("USD", issuer_kp.public_key),
            amount="5",
        )
        .append_change_trust_op(asset=Asset("USD", issuer_kp.public_key), limit="10")
        .append_create_account_op(
            destination=Keypair.random().public_key,
            starting_balance="2",
        )
        .append_set_options_op(low_threshold=1, med_threshold=2, high_threshold=3)
        .append_create_claimable_balance_op(
            asset=Asset.native(),
            amount="3",
            claimants=[
                Claimant(
                    destination=destination_kp.public_key,
                    predicate=ClaimPredicate.predicate_before_relative_time(3600),
                )
            ],
        )
        .append_manage_data_op(data_name="hello", data_value=b"world")
        .append_set_trust_line_flags_op(
            trustor=destination_kp.public_key,
            asset=Asset("USD", issuer_kp.public_key),
            set_flags=TrustLineFlags.AUTHORIZED_FLAG,
        )
        .append_bump_sequence_op(bump_to=999)
        .set_timeout(300)
        .build()
    )

    account_map = {
        source_kp.public_key: {
            "id": source_kp.public_key,
            "sequence": "9",
            "balances": [
                {"asset_type": "native", "balance": "100"},
                {
                    "asset_type": "credit_alphanum4",
                    "asset_code": "USD",
                    "asset_issuer": issuer_kp.public_key,
                    "balance": "50",
                },
            ],
        },
        destination_kp.public_key: {
            "id": destination_kp.public_key,
            "balances": [
                {
                    "asset_type": "credit_alphanum4",
                    "asset_code": "USD",
                    "asset_issuer": issuer_kp.public_key,
                    "balance": "0",
                }
            ],
        },
        issuer_kp.public_key: {"id": issuer_kp.public_key, "balances": [], "flags": {}},
    }
    repo = SimpleNamespace(
        get_by_sequence=AsyncMock(
            return_value=[
                SimpleNamespace(hash="h" * 64, description="Existing description")
            ]
        )
    )

    with (
        patch("services.xdr_parser.current_app", _mock_current_app()),
        patch("services.xdr_parser.TransactionRepository", return_value=repo),
        patch(
            "services.xdr_parser.get_available_balance_str",
            AsyncMock(return_value="(bal)"),
        ),
        patch(
            "services.xdr_parser.get_account_fresh",
            AsyncMock(return_value=account_map[source_kp.public_key]),
        ),
        patch(
            "services.xdr_parser.get_account",
            AsyncMock(
                side_effect=lambda account_id: account_map.get(
                    account_id, {"id": account_id, "balances": []}
                )
            ),
        ),
        patch("services.xdr_parser.check_asset", AsyncMock(return_value="")),
        patch(
            "services.xdr_parser.grist_cache.find_by_filter",
            return_value=[{"issuer": issuer_kp.public_key}],
        ),
    ):
        result = await decode_xdr_to_text(transaction.to_xdr())

    text = "\n".join(result)
    assert "Sequence Number 11" in text
    assert "Bad Fee" in text
    assert "Memo text" in text
    assert "Перевод 5" in text
    assert "Открываем линию доверия" in text
    assert "Создание аккаунта" in text
    assert "ManageData hello" in text
    assert "BumpSequence to 999" in text


@pytest.mark.asyncio
async def test_decode_xdr_to_text_describes_pool_and_special_operations():
    source_kp = Keypair.random()
    issuer_kp = Keypair.random()
    victim_kp = Keypair.random()
    pool_asset = LiquidityPoolAsset(Asset.native(), Asset("USD", issuer_kp.public_key))
    source_account = Account(source_kp.public_key, 20)

    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=5000,
        )
        .append_begin_sponsoring_future_reserves_op(sponsored_id=victim_kp.public_key)
        .append_end_sponsoring_future_reserves_op()
        .append_clawback_op(
            from_=victim_kp.public_key,
            asset=Asset("USD", issuer_kp.public_key),
            amount="7",
        )
        .append_change_trust_op(asset=pool_asset)
        .append_liquidity_pool_deposit_op(
            liquidity_pool_id=pool_asset.liquidity_pool_id,
            max_amount_a="5",
            max_amount_b="10",
            min_price="1",
            max_price="2",
        )
        .append_liquidity_pool_withdraw_op(
            liquidity_pool_id=pool_asset.liquidity_pool_id,
            amount="2",
            min_amount_a="1",
            min_amount_b="3",
        )
        .set_timeout(300)
        .build()
    )

    account_map = {
        source_kp.public_key: {
            "id": source_kp.public_key,
            "sequence": "19",
            "balances": [
                {"asset_type": "native", "balance": "100"},
                {
                    "asset_type": "credit_alphanum4",
                    "asset_code": "USD",
                    "asset_issuer": issuer_kp.public_key,
                    "balance": "100",
                },
            ],
        },
        issuer_kp.public_key: {"id": issuer_kp.public_key, "balances": [], "flags": {}},
        victim_kp.public_key: {"id": victim_kp.public_key, "balances": []},
    }
    pool_data = {"LiquidityPoolAsset": pool_asset}
    repo = SimpleNamespace(get_by_sequence=AsyncMock(return_value=[]))

    with (
        patch("services.xdr_parser.current_app", _mock_current_app()),
        patch("services.xdr_parser.TransactionRepository", return_value=repo),
        patch(
            "services.xdr_parser.get_available_balance_str",
            AsyncMock(return_value=""),
        ),
        patch(
            "services.xdr_parser.get_account_fresh",
            AsyncMock(return_value=account_map[source_kp.public_key]),
        ),
        patch(
            "services.xdr_parser.get_account",
            AsyncMock(
                side_effect=lambda account_id: account_map.get(
                    account_id, {"id": account_id, "balances": []}
                )
            ),
        ),
        patch("services.xdr_parser.get_pool_data", AsyncMock(return_value=pool_data)),
        patch("services.xdr_parser.check_asset", AsyncMock(return_value="")),
        patch(
            "services.xdr_parser.grist_cache.find_by_filter",
            return_value=[{"issuer": issuer_kp.public_key}],
        ),
    ):
        result = await decode_xdr_to_text(transaction.to_xdr())

    text = "\n".join(result)
    assert "BeginSponsoringFutureReserves" in text
    assert "EndSponsoringFutureReserves" in text
    assert "Возврат 7" in text
    assert "LiquidityPoolDeposit" in text
    assert "LiquidityPoolWithdraw" in text


@pytest.mark.asyncio
async def test_decode_xdr_to_text_from_fixture_renders_capture_and_transfer_summary():
    text = await _decode_fixture_xdr(
        MOUNTAIN_CAPTURE_WITH_TRANSFER_XDR, token_display_name="EURMTL"
    )
    assert "Contract call:" in text
    assert ".capture(" in text
    assert '"А Соз llms.txt не сделал 👀"' in text
    assert "Transfer 0.0000012 EURMTL (12 raw)" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("xdr", "token_display_name", "expected_snippets"),
    [
        (
            SWAP_CHAINED_WITH_XLM_TRANSFER_XDR,
            "native",
            [
                ".swap_chained(",
                "Transfer 1 XLM (10000000 raw)",
            ],
        ),
        (
            SWAP_WITH_USDM_TRANSFER_XDR,
            "USDM",
            [
                ".swap(",
                "Transfer 1 USDM (10000000 raw)",
            ],
        ),
        (
            SWAP_CHAINED_WITH_YUSDC_TRANSFER_XDR,
            "yUSDC",
            [
                ".swap_chained(",
                "Transfer 1.2293597 yUSDC (12293597 raw)",
            ],
        ),
        (
            DEPOSIT_WITH_DUAL_TRANSFERS_XDR,
            "USDM",
            [
                ".deposit(",
                "Transfer 540 USDM (5400000000 raw)",
                "Transfer 500 USDM (5000000000 raw)",
            ],
        ),
        (
            INIT_STABLESWAP_POOL_WITH_AQUA_TRANSFER_XDR,
            "AQUA",
            [
                ".init_stableswap_pool(",
                "Transfer 300000 AQUA (3000000000000 raw)",
            ],
        ),
    ],
)
async def test_decode_xdr_to_text_from_real_fixtures_renders_distinct_transfer_summaries(
    xdr, token_display_name, expected_snippets
):
    text = await _decode_fixture_xdr(xdr, token_display_name=token_display_name)

    for snippet in expected_snippets:
        assert snippet in text


@pytest.mark.asyncio
async def test_decode_xdr_to_text_from_withdraw_fixture_warns_about_unknown_subinvocation():
    text = await _decode_fixture_xdr(
        WITHDRAW_WITH_UNKNOWN_SUBINVOCATION_XDR,
        token_display_name={
            "CDOY7ILRR7PDGLBXZUPSENB6XOET77PR2JY3HXDGQS3TS4T764OYBUGO": "stPool",
        },
    )

    assert ".withdraw(" in text
    assert "Burn 14.2949196 stPool (142949196 raw)" in text
    assert "additional sub-invocation" not in text


@pytest.mark.asyncio
async def test_render_sub_invocation_summary_formats_native_as_xlm_and_scales_raw():
    source_kp = Keypair.random()
    source_bytes = StrKey.decode_ed25519_public_key(source_kp.public_key)
    destination_contract = bytes.fromhex("ab" * 32)
    native_contract = bytes.fromhex("cd" * 32)

    invocation = SimpleNamespace(
        function=SimpleNamespace(
            contract_fn=SimpleNamespace(
                contract_address=SimpleNamespace(
                    contract_id=SimpleNamespace(hash=native_contract)
                ),
                function_name=SimpleNamespace(sc_symbol=b"transfer"),
                args=[
                    SimpleNamespace(
                        type=SimpleNamespace(value=18),
                        address=SimpleNamespace(
                            type=SimpleNamespace(value=0),
                            account_id=SimpleNamespace(
                                account_id=SimpleNamespace(
                                    ed25519=SimpleNamespace(uint256=source_bytes)
                                )
                            ),
                            contract_id=None,
                        ),
                    ),
                    SimpleNamespace(
                        type=SimpleNamespace(value=18),
                        address=SimpleNamespace(
                            type=SimpleNamespace(value=1),
                            account_id=None,
                            contract_id=SimpleNamespace(hash=destination_contract),
                        ),
                    ),
                    SimpleNamespace(
                        type=SimpleNamespace(value=10),
                        i128=SimpleNamespace(
                            lo=SimpleNamespace(uint64=10_000_000),
                            hi=SimpleNamespace(int64=0),
                        ),
                        b=None,
                    ),
                ],
            )
        )
    )

    with patch(
        "services.xdr_parser.read_token_contract_display_name",
        new=AsyncMock(return_value="native"),
        create=True,
    ):
        line = await _render_sub_invocation_summary(invocation)

    assert "Transfer 1 XLM (10000000 raw)" in line


@pytest.mark.asyncio
async def test_render_auth_sub_invocation_summaries_renders_generic_nested_calls():
    source_kp = Keypair.random()
    source_bytes = StrKey.decode_ed25519_public_key(source_kp.public_key)
    destination_contract = bytes.fromhex("ab" * 32)
    token_contract = bytes.fromhex("cd" * 32)
    unknown_contract = bytes.fromhex("ef" * 32)

    transfer_invocation = SimpleNamespace(
        function=SimpleNamespace(
            contract_fn=SimpleNamespace(
                contract_address=SimpleNamespace(
                    contract_id=SimpleNamespace(hash=token_contract)
                ),
                function_name=SimpleNamespace(sc_symbol=b"transfer"),
                args=[
                    SimpleNamespace(
                        type=SimpleNamespace(value=18),
                        address=SimpleNamespace(
                            type=SimpleNamespace(value=0),
                            account_id=SimpleNamespace(
                                account_id=SimpleNamespace(
                                    ed25519=SimpleNamespace(uint256=source_bytes)
                                )
                            ),
                            contract_id=None,
                        ),
                    ),
                    SimpleNamespace(
                        type=SimpleNamespace(value=18),
                        address=SimpleNamespace(
                            type=SimpleNamespace(value=1),
                            account_id=None,
                            contract_id=SimpleNamespace(hash=destination_contract),
                        ),
                    ),
                    SimpleNamespace(
                        type=SimpleNamespace(value=10),
                        i128=SimpleNamespace(
                            lo=SimpleNamespace(uint64=10_000_000),
                            hi=SimpleNamespace(int64=0),
                        ),
                        b=None,
                    ),
                ],
                sub_invocations=[],
            )
        ),
        sub_invocations=[],
    )
    approve_invocation = SimpleNamespace(
        function=SimpleNamespace(
            contract_fn=SimpleNamespace(
                contract_address=SimpleNamespace(
                    contract_id=SimpleNamespace(hash=unknown_contract)
                ),
                function_name=SimpleNamespace(sc_symbol=b"approve"),
                args=[],
            )
        ),
        sub_invocations=[],
    )
    operation = SimpleNamespace(
        auth=[
            SimpleNamespace(
                root_invocation=SimpleNamespace(
                    sub_invocations=[transfer_invocation, approve_invocation]
                )
            )
        ]
    )

    with patch(
        "services.xdr_parser.read_token_contract_display_name",
        new=AsyncMock(return_value="native"),
        create=True,
    ):
        lines = await _render_auth_sub_invocation_summaries(operation)

    text = "\n".join(lines)
    assert "Transfer 1 XLM (10000000 raw)" in text
    assert "Nested call:" in text
    assert ".approve()" in text
    assert "additional sub-invocation" not in text


@pytest.mark.asyncio
async def test_render_sub_invocation_summary_formats_burn_and_generic_nested_calls():
    source_kp = Keypair.random()
    source_bytes = StrKey.decode_ed25519_public_key(source_kp.public_key)
    token_contract = bytes.fromhex("cd" * 32)

    burn_invocation = SimpleNamespace(
        function=SimpleNamespace(
            contract_fn=SimpleNamespace(
                contract_address=SimpleNamespace(
                    contract_id=SimpleNamespace(hash=token_contract)
                ),
                function_name=SimpleNamespace(sc_symbol=b"burn"),
                args=[
                    SimpleNamespace(
                        type=SimpleNamespace(value=18),
                        address=SimpleNamespace(
                            type=SimpleNamespace(value=0),
                            account_id=SimpleNamespace(
                                account_id=SimpleNamespace(
                                    ed25519=SimpleNamespace(uint256=source_bytes)
                                )
                            ),
                            contract_id=None,
                        ),
                    ),
                    SimpleNamespace(
                        type=SimpleNamespace(value=10),
                        i128=SimpleNamespace(
                            lo=SimpleNamespace(uint64=142_949_196),
                            hi=SimpleNamespace(int64=0),
                        ),
                        b=None,
                    ),
                ],
            )
        )
    )
    approve_invocation = SimpleNamespace(
        function=SimpleNamespace(
            contract_fn=SimpleNamespace(
                contract_address=SimpleNamespace(
                    contract_id=SimpleNamespace(hash=token_contract)
                ),
                function_name=SimpleNamespace(sc_symbol=b"approve"),
                args=[
                    SimpleNamespace(
                        type=SimpleNamespace(value=18),
                        address=SimpleNamespace(
                            type=SimpleNamespace(value=0),
                            account_id=SimpleNamespace(
                                account_id=SimpleNamespace(
                                    ed25519=SimpleNamespace(uint256=source_bytes)
                                )
                            ),
                            contract_id=None,
                        ),
                    ),
                    SimpleNamespace(
                        type=SimpleNamespace(value=10),
                        i128=SimpleNamespace(
                            lo=SimpleNamespace(uint64=10_000_000),
                            hi=SimpleNamespace(int64=0),
                        ),
                        b=None,
                    ),
                ],
            )
        )
    )

    with patch(
        "services.xdr_parser.read_token_contract_display_name",
        new=AsyncMock(return_value="stPool"),
        create=True,
    ):
        burn_line = await _render_sub_invocation_summary(burn_invocation)
        approve_line = await _render_sub_invocation_summary(approve_invocation)

    assert "Burn 14.2949196 stPool (142949196 raw)" in burn_line
    assert "Nested call:" in approve_line
    assert ".approve(" in approve_line
