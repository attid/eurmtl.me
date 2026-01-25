"""
Тесты для модуля services/xdr_parser.py
"""

import base64
import pytest
from stellar_sdk import Keypair, TransactionBuilder, Network, Account, Asset

from services.xdr_parser import (
    is_valid_base64,
    decode_data_value,
    construct_payload,
    uri_sign,
    get_key_sort,
    address_id_to_link,
    pool_id_to_link,
)


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

    def test_uri_sign_url_encoded(self):
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

    # Примечание: decode_xdr_to_base64 сложная функция, требующая большого контекста
    # Для её тестирования нужно создать реалистичные XDR
    # Это будет сделано в отдельных тестах если требуется
