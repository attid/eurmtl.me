import pytest
from unittest.mock import patch, MagicMock

from stellar_sdk import (
    Keypair,
    Asset,
    Network,
    TransactionBuilder,
    Account,
)
from stellar_sdk.operation import Payment, AccountMerge, SetOptions

from services.stellar_client import extract_sources, main_fund_address


# --- Тест 0: Интеграционный тест с реальным Horizon API ---


@pytest.mark.integration
@pytest.mark.asyncio
async def test_horizon_account_response_format():
    """Проверяет формат ответа от Horizon для реального аккаунта."""
    from other.web_tools import http_session_manager

    response = await http_session_manager.get_web_request(
        "GET",
        f"https://horizon.stellar.org/accounts/{main_fund_address}",
        return_type="json",
    )

    assert response.status == 200
    data = response.data
    assert "thresholds" in data
    assert isinstance(data["thresholds"], dict)
    assert "low_threshold" in data["thresholds"]
    assert "med_threshold" in data["thresholds"]
    assert "high_threshold" in data["thresholds"]


# --- Утилиты для мок-тестов ---


def mock_horizon_response(low, med, high):
    """Создает мок-ответ от Horizon."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.data = {
        "thresholds": {
            "low_threshold": low,
            "med_threshold": med,
            "high_threshold": high,
        },
        "signers": [],  # Для простоты оставляем пустым
    }
    return mock_resp


def create_test_transaction_builder(source_kp, operations):
    """Создает TransactionBuilder для тестов."""
    import time

    source_account = Account(source_kp.public_key, 12345)
    tx_builder = TransactionBuilder(
        source_account=source_account,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        base_fee=100,
    )
    # Добавляем TimeBounds чтобы убрать warning
    tx_builder.set_timeout(300)  # 5 minutes timeout
    for op in operations:
        tx_builder.append_operation(op)
    return tx_builder


# --- Тесты с моками ---


@pytest.mark.asyncio
@patch("services.stellar_client.http_session_manager.get_web_request")
async def test_extract_sources_for_medium_threshold(mock_get, app):
    """Тест 1: Транзакция со средним порогом."""
    async with app.app_context():
        source_kp = Keypair.random()
        mock_get.return_value = mock_horizon_response(low=2, med=5, high=10)

        ops = [
            Payment(
                destination=Keypair.random().public_key,
                asset=Asset.native(),
                amount="10",
            )
        ]
        tx_builder = create_test_transaction_builder(source_kp, ops)
        tx_envelope = tx_builder.build()

        sources = await extract_sources(tx_envelope.to_xdr())
        print(sources)

        assert source_kp.public_key in sources
        assert sources[source_kp.public_key]["threshold"] == 5  # medium_threshold


@pytest.mark.asyncio
@patch("services.stellar_client.http_session_manager.get_web_request")
async def test_extract_sources_for_high_threshold(mock_get, app):
    """Тест 2: Транзакция с высоким порогом."""
    async with app.app_context():
        source_kp = Keypair.random()
        mock_get.return_value = mock_horizon_response(low=2, med=5, high=10)

        ops = [
            Payment(
                destination=Keypair.random().public_key,
                asset=Asset.native(),
                amount="10",
            ),
            AccountMerge(destination=Keypair.random().public_key),
        ]
        tx_builder = create_test_transaction_builder(source_kp, ops)
        tx_envelope = tx_builder.build()

        sources = await extract_sources(tx_envelope.to_xdr())

        assert sources[source_kp.public_key]["threshold"] == 10  # high_threshold


@pytest.mark.asyncio
@patch("services.stellar_client.http_session_manager.get_web_request")
async def test_extract_sources_with_multiple_sources(mock_get, app):
    """Тест 3: Транзакция с несколькими источниками."""
    async with app.app_context():
        main_source_kp = Keypair.random()
        op_source_kp = Keypair.random()

        # Настраиваем мок для ответа на запросы для обоих аккаунтов
        def side_effect(method, url, **kwargs):
            if main_source_kp.public_key in url:
                return mock_horizon_response(low=2, med=5, high=10)
            if op_source_kp.public_key in url:
                return mock_horizon_response(low=20, med=50, high=100)
            return MagicMock(status=404)

        mock_get.side_effect = side_effect

        ops = [
            Payment(
                destination=Keypair.random().public_key,
                asset=Asset.native(),
                amount="10",
            ),  # Источник - main_source (medium)
            SetOptions(
                low_threshold=1, source=op_source_kp.public_key
            ),  # Источник - op_source (high)
        ]
        tx_builder = create_test_transaction_builder(main_source_kp, ops)
        tx_envelope = tx_builder.build()

        sources = await extract_sources(tx_envelope.to_xdr())
        print(sources)

        assert len(sources) == 2
        assert sources[main_source_kp.public_key]["threshold"] == 5  # medium
        assert sources[op_source_kp.public_key]["threshold"] == 100  # high


@pytest.mark.asyncio
@patch("services.stellar_client.http_session_manager.get_web_request")
async def test_extract_sources_handles_network_error(mock_get, app):
    """Тест 4: Обработка ошибки сети."""
    async with app.app_context():
        source_kp = Keypair.random()
        mock_get.side_effect = Exception("Network Error")

        ops = [
            Payment(
                destination=Keypair.random().public_key,
                asset=Asset.native(),
                amount="10",
            )
        ]
        tx_builder = create_test_transaction_builder(source_kp, ops)
        tx_envelope = tx_builder.build()

        sources = await extract_sources(tx_envelope.to_xdr())
        print(sources)

        assert sources[source_kp.public_key]["threshold"] == 0
