"""
Тесты для модуля services/stellar_client.py
"""

import pytest
from stellar_sdk import Asset, Keypair

from services.stellar_client import (
    float2str,
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


# Примечание: Остальные функции в stellar_client.py (check_publish_state,
# get_pool_data, check_asset, и т.д.) являются async и требуют:
# - Доступа к Horizon API
# - Доступа к базе данных через current_app.db_pool
# - Сложного состояния и моков
#
# Эти функции уже частично покрыты в:
# - tests/test_extract_sources.py (extract_sources, get_operation_threshold_level)
# - tests/services/test_transaction_service.py
# - tests/routers/test_*.py (интеграционные тесты роутов)
#
# Для значительного повышения coverage этих функций потребуется:
# 1. Создание сложных моков для Horizon API
# 2. Создание моков для базы данных
# 3. Большое количество интеграционных тестов
#
# Это может быть выполнено в следующих итерациях.
