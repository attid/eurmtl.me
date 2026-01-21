
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from quart import Quart

# Импортируем тестируемую функцию
from services.stellar_client import check_user_in_sign
from db.sql_models import Transactions, Signers, Signatures

@pytest.fixture
def app():
    app = Quart(__name__)
    app.db_pool = MagicMock()
    return app

# --- Тесты для check_user_in_sign ---

@pytest.mark.asyncio
@patch('services.stellar_client.session', {})
async def test_not_logged_in(app):
    """Тест 1: Пользователь не авторизован."""
    async with app.app_context():
        assert await check_user_in_sign('some_hash') is False

@pytest.mark.asyncio
@patch('services.stellar_client.session', {'user_id': '84131737'})
async def test_is_admin(app):
    """Тест 2: Пользователь - админ."""
    async with app.app_context():
        assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('services.stellar_client.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('services.stellar_client.session', {'user_id': '12345'})
async def test_is_transaction_owner(mock_get_secretaries, app):
    """Тест 3: Пользователь - владелец транзакции."""
    mock_transaction = Transactions(owner_id='12345')
    
    mock_db_session = MagicMock()
    # Setup async execute result
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_transaction
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    # Setup async context manager for db_pool
    mock_pool_cm = AsyncMock()
    mock_pool_cm.__aenter__.return_value = mock_db_session
    app.db_pool.return_value = mock_pool_cm

    async with app.app_context():
        assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('services.stellar_client.get_secretaries', new_callable=AsyncMock)
@patch('services.stellar_client.session', {'user_id': '12345'})
async def test_is_secretary(mock_get_secretaries, app):
    """Тест 4: Пользователь - секретарь."""
    mock_transaction = Transactions(owner_id='999', source_account='G_SOURCE')
    mock_get_secretaries.return_value = {'G_SOURCE': ['12345']}
    
    mock_db_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_transaction
    
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    mock_pool_cm = AsyncMock()
    mock_pool_cm.__aenter__.return_value = mock_db_session
    app.db_pool.return_value = mock_pool_cm

    async with app.app_context():
        assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('services.stellar_client.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('services.stellar_client.session', {'user_id': '12345'})
async def test_is_signer_who_signed(mock_get_secretaries, app):
    """Тест 5: Пользователь - подписант, который подписал."""
    mock_transaction = Transactions(owner_id='999')
    mock_signer = Signers(id=777)
    mock_signature = Signatures()

    async def execute_side_effect(statement):
        # We need to inspect the statement to decide what to return.
        # However, checking the statement object structure might be complex.
        # Alternatively, we can sequence return values if we know the order of calls.
        # 1. Transactions check
        # 2. Signers check
        # 3. Signatures check
        pass # Only useful if we implement complex logic

    # Simplified approach using side_effect with an iterator or list
    mock_result_tx = MagicMock()
    mock_result_tx.scalars.return_value.first.return_value = mock_transaction
    
    # Secretaries check is skipped or empty

    mock_result_signer = MagicMock()
    mock_result_signer.scalars.return_value.first.return_value = mock_signer

    mock_result_signature = MagicMock()
    mock_result_signature.scalars.return_value.first.return_value = mock_signature

    mock_db_session = MagicMock()
    mock_db_session.execute = AsyncMock(side_effect=[mock_result_tx, mock_result_signer, mock_result_signature])

    mock_pool_cm = AsyncMock()
    mock_pool_cm.__aenter__.return_value = mock_db_session
    app.db_pool.return_value = mock_pool_cm

    async with app.app_context():
        assert await check_user_in_sign('some_hash') is True

@pytest.mark.asyncio
@patch('services.stellar_client.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('services.stellar_client.session', {'user_id': '12345'})
async def test_is_signer_who_did_not_sign(mock_get_secretaries, app):
    """Тест 6: Пользователь - подписант, который НЕ подписал."""
    mock_transaction = Transactions(owner_id='999')
    mock_signer = Signers(id=777)

    mock_result_tx = MagicMock()
    mock_result_tx.scalars.return_value.first.return_value = mock_transaction

    mock_result_signer = MagicMock()
    mock_result_signer.scalars.return_value.first.return_value = mock_signer

    mock_result_signature = MagicMock()
    mock_result_signature.scalars.return_value.first.return_value = None

    mock_db_session = MagicMock()
    mock_db_session.execute = AsyncMock(side_effect=[mock_result_tx, mock_result_signer, mock_result_signature])

    mock_pool_cm = AsyncMock()
    mock_pool_cm.__aenter__.return_value = mock_db_session
    app.db_pool.return_value = mock_pool_cm

    async with app.app_context():
        assert await check_user_in_sign('some_hash') is False

@pytest.mark.asyncio
@patch('services.stellar_client.get_secretaries', new_callable=AsyncMock, return_value={})
@patch('services.stellar_client.session', {'user_id': '12345'})
async def test_not_related_user(mock_get_secretaries, app):
    """Тест 7: Пользователь не имеет отношения к транзакции."""
    mock_transaction = Transactions(owner_id='999')
    
    mock_result_tx = MagicMock()
    mock_result_tx.scalars.return_value.first.return_value = mock_transaction

    mock_result_signer = MagicMock()
    mock_result_signer.scalars.return_value.first.return_value = None # Not a signer

    mock_db_session = MagicMock()
    mock_db_session.execute = AsyncMock(side_effect=[mock_result_tx, mock_result_signer])

    mock_pool_cm = AsyncMock()
    mock_pool_cm.__aenter__.return_value = mock_db_session
    app.db_pool.return_value = mock_pool_cm

    async with app.app_context():
        assert await check_user_in_sign('some_hash') is False

