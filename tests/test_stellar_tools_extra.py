
import pytest
from stellar_sdk import (
    TransactionBuilder,
    Network,
    Keypair,
    Account,
    Asset,
    TextMemo,
)

# Импортируем тестируемую функцию
from other.stellar_tools import update_memo_in_xdr, TransactionEnvelope

# --- Вспомогательная функция для создания XDR ---

def create_test_xdr(memo_text=None):
    """Создает простой XDR для тестов."""
    source_kp = Keypair.random()
    source_account = Account(source_kp.public_key, 12345)
    
    builder = TransactionBuilder(
        source_account=source_account,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        base_fee=100
    )
    
    if memo_text:
        builder.add_memo(TextMemo(memo_text))
        
    # Добавляем любую операцию, чтобы транзакция была валидной
    builder.append_payment_op(
        destination=Keypair.random().public_key,
        asset=Asset.native(),
        amount="1"
    )
    
    tx_envelope = builder.build()
    return tx_envelope.to_xdr()

# --- Тесты ---

def test_update_memo_successful():
    """
    Проверяет успешное добавление и обновление memo.
    """
    # 1. Создаем XDR без memo
    xdr_no_memo = create_test_xdr()
    new_memo_text = "Hello, Stellar!"

    # 2. Обновляем XDR, добавляя memo
    updated_xdr = update_memo_in_xdr(xdr_no_memo, new_memo_text)

    # 3. Проверяем результат
    tx_env_updated = TransactionEnvelope.from_xdr(updated_xdr, Network.PUBLIC_NETWORK_PASSPHRASE)
    
    assert isinstance(tx_env_updated.transaction.memo, TextMemo)
    assert tx_env_updated.transaction.memo.memo_text.decode('utf-8') == new_memo_text

    # 4. Проверяем, что операция осталась на месте
    assert len(tx_env_updated.transaction.operations) == 1

def test_update_memo_invalid_xdr():
    """
    Проверяет, что функция вызывает исключение при невалидном XDR.
    """
    invalid_xdr = "this is not a valid xdr"
    
    with pytest.raises(Exception) as excinfo:
        update_memo_in_xdr(invalid_xdr, "some memo")
        
    # Проверяем, что исключение содержит осмысленное сообщение
    assert "Error updating memo" in str(excinfo.value)

