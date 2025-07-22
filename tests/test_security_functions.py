
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Импортируем тестируемую функцию
from other.stellar_tools import check_user_in_sign
from db.sql_models import Transactions, Signers, Signatures

# --- Тесты для check_user_in_sign ---

@pytest.mark.asyncio
@patch('other.stellar_tools.session', {})
async def test_not_logged_in():
    """Тест 1: Пользователь не авторизован."""
    assert await check_user_in_sign('some_hash') is False

@pytest.mark.asyncio
@patch('other.stellar_tools.session', {'user_id': '84131737'})
async def test_is_admin():
    """Тест 2: Пользователь - админ."""
    assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('other.stellar_tools.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('other.stellar_tools.db_pool')
@patch('other.stellar_tools.session', {'user_id': '12345'})
async def test_is_transaction_owner(mock_db_pool, mock_get_secretaries):
    """Тест 3: Пользователь - владелец транзакции."""
    mock_transaction = Transactions(owner_id='12345')
    
    mock_db_session = MagicMock()
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_transaction
    mock_db_pool.return_value.__enter__.return_value = mock_db_session

    assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('other.stellar_tools.get_secretaries', new_callable=AsyncMock)
@patch('other.stellar_tools.db_pool')
@patch('other.stellar_tools.session', {'user_id': '12345'})
async def test_is_secretary(mock_db_pool, mock_get_secretaries):
    """Тест 4: Пользователь - секретарь."""
    mock_transaction = Transactions(owner_id='999', source_account='G_SOURCE')
    mock_get_secretaries.return_value = {'G_SOURCE': ['12345']}
    
    mock_db_session = MagicMock()
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_transaction
    mock_db_pool.return_value.__enter__.return_value = mock_db_session

    assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('other.stellar_tools.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('other.stellar_tools.db_pool')
@patch('other.stellar_tools.session', {'user_id': '12345'})
async def test_is_signer_who_signed(mock_db_pool, mock_get_secretaries):
    """Тест 5: Пользователь - подписант, который подписал."""
    mock_transaction = Transactions(owner_id='999')
    mock_signer = Signers(id=777)
    mock_signature = Signatures()

    def query_side_effect(model):
        if model == Transactions:
            return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_transaction))))
        if model == Signers:
            return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_signer))))
        if model == Signatures:
            return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_signature))))
        return MagicMock()

    mock_db_session = MagicMock()
    mock_db_session.query.side_effect = query_side_effect
    mock_db_pool.return_value.__enter__.return_value = mock_db_session

    assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('other.stellar_tools.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('other.stellar_tools.db_pool')
@patch('other.stellar_tools.session', {'user_id': '12345'})
async def test_is_signer_who_did_not_sign(mock_db_pool, mock_get_secretaries):
    """Тест 6: Пользователь - подписант, который НЕ подписал."""
    mock_transaction = Transactions(owner_id='999')
    mock_signer = Signers(id=777)

    def query_side_effect(model):
        if model == Transactions:
            return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_transaction))))
        if model == Signers:
            return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_signer))))
        if model == Signatures:
            return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))) # Не находит подпись
        return MagicMock()

    mock_db_session = MagicMock()
    mock_db_session.query.side_effect = query_side_effect
    mock_db_pool.return_value.__enter__.return_value = mock_db_session

    assert await check_user_in_sign('some_hash') is False

@pytest.mark.asyncio
@patch('other.stellar_tools.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('other.stellar_tools.db_pool')
@patch('other.stellar_tools.session', {'user_id': '12345'})
async def test_not_related_user(mock_db_pool, mock_get_secretaries):
    """Тест 7: Пользователь не имеет отношения к транзакции."""
    mock_transaction = Transactions(owner_id='999')
    
    def query_side_effect(model):
        if model == Transactions:
            return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_transaction))))
        # Для Signers и Signatures возвращаем None
        return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None))))

    mock_db_session = MagicMock()
    mock_db_session.query.side_effect = query_side_effect
    mock_db_pool.return_value.__enter__.return_value = mock_db_session

    assert await check_user_in_sign('some_hash') is False

