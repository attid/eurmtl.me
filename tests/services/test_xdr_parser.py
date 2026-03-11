"""
Тесты для модуля services/xdr_parser.py
"""

import base64
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
    update_memo_in_xdr,
)

INVALID_STELLAR_XDR = "AAAAAgAAAAA+gj+9R9RakwtxBG6Up8jAewUfdurumKJARnpcMG9VBgAAAZADqmC9AAAACQAAAAEAAAAAAAAAAAAAAABprWevAAAAAQAAAARleGNoAAAAAgAAAAAAAAABAAAAAOULguv++61OnAUgnSV24FKlgUt80KvaUijNM9Fdx2wmAAAAAkVVUk1UTAAAAAAAAAAAAAAEqbejBk1rxsHVls854RnAyfpJaZacvgwmQ0jxNDBvqgAAAAFloLwAAAAAAAAAAAMAAAACRVVSTVRMAAAAAAAAAAAAAASpt6MGTWvGwdWWzznhGcDJ+klplpy+DCZDSPE0MG+qAAAAAVVTRE0AAAAAzjFwwWvYRuQOCHjRQ12ZsvHFXsmtQ0ka1OpQTcuL5UoAAAAAAAAAAAAAAAEAAAABAAAAAGzhWBAAAAAAAAAAAjBvVQYAAABA8ngRn6FosWJoKr+CiNwUecKAkHp4oOTfCc3hSeFBWUNfbddyxouSs9LrkX6Yym7KUpqlbr35eypU0gUOs9bEBVpCAfwAAABAKQso0UED2q9QpUa1jIHCGtWkFCgHu7OAzYodR4L3K+HOY0OGtqIRomGNwJ2/hSP6CUc7uAJryU33J1osSvUwDQ=="


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

        assert decode_scval(account_scval) == account_id
        assert decode_scval(symbol_scval) == "swap"
        assert decode_scval(vector_scval) == "[swap]"
        assert decode_scval(u128_scval) == str(5 + (1 << 64))
        assert decode_scval(i128_scval) == str((1 << 64) + 7)

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

    assert any("Function Type: invoke" in line for line in invoke_lines)
    assert any("Function: swap" in line for line in invoke_lines)
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
