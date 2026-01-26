import pytest
from unittest.mock import patch, AsyncMock

# Импортируем тестируемую функцию
from services.stellar_client import check_user_in_sign

# --- Тесты для check_user_in_sign ---


@pytest.mark.asyncio
@patch("services.stellar_client.session", {})
async def test_not_logged_in(app):
    """Тест 1: Пользователь не авторизован."""
    async with app.app_context():
        assert await check_user_in_sign("some_hash") is False


@pytest.mark.asyncio
@patch("services.stellar_client.session", {"user_id": "84131737"})
async def test_is_admin(app):
    """Тест 2: Пользователь - админ."""
    async with app.app_context():
        assert await check_user_in_sign("some_hash") is True


@pytest.mark.asyncio
@patch(
    "services.stellar_client.get_secretaries", new_callable=AsyncMock, return_value={}
)
@patch("services.stellar_client.session", {"user_id": "12345678"})
async def test_is_transaction_owner(
    mock_get_secretaries, app, db_session, seed_transactions
):
    """Тест 3: Пользователь - владелец транзакции (использует seed данные)."""
    # Транзакция 'a'*64 принадлежит @alice (owner_id=12345678)
    async with app.app_context():
        assert await check_user_in_sign("a" * 64) is True


@pytest.mark.asyncio
@patch("services.stellar_client.get_secretaries", new_callable=AsyncMock)
@patch("services.stellar_client.session", {"user_id": "34567890"})
async def test_is_secretary(
    mock_get_secretaries, app, db_session, seed_transactions, seed_signers
):
    """Тест 4: Пользователь - секретарь."""
    # @charlie (tg_id=34567890) является секретарем для alice_pk
    alice_pk = seed_signers[1].public_key
    mock_get_secretaries.return_value = {alice_pk: ["34567890"]}

    async with app.app_context():
        # Транзакция 'a'*64 имеет source_account=alice_pk
        assert await check_user_in_sign("a" * 64) is True


@pytest.mark.asyncio
@patch(
    "services.stellar_client.get_secretaries", new_callable=AsyncMock, return_value={}
)
@patch("services.stellar_client.session", {"user_id": "12345678"})
async def test_is_signer_who_signed(
    mock_get_secretaries, app, db_session, seed_signatures
):
    """Тест 5: Пользователь - подписант, который подписал."""
    # @alice (tg_id=12345678, signer_id=2) подписала транзакцию 'a'*64
    async with app.app_context():
        assert await check_user_in_sign("a" * 64) is True


@pytest.mark.asyncio
@patch(
    "services.stellar_client.get_secretaries", new_callable=AsyncMock, return_value={}
)
@patch("services.stellar_client.session", {"user_id": "23456789"})
async def test_is_signer_who_did_not_sign(
    mock_get_secretaries, app, db_session, seed_signatures
):
    """Тест 6: Пользователь - подписант, который НЕ подписал (скрытая подпись)."""
    # @bob (tg_id=23456789, signer_id=3) имеет скрытую подпись для 'a'*64
    # Должен вернуть False, так как подпись скрыта (hidden=1)
    async with app.app_context():
        # Используем транзакцию 'c'*64, где @bob не подписывал
        assert await check_user_in_sign("c" * 64) is False


@pytest.mark.asyncio
@patch(
    "services.stellar_client.get_secretaries", new_callable=AsyncMock, return_value={}
)
@patch("services.stellar_client.session", {"user_id": "99999999"})
async def test_not_related_user(
    mock_get_secretaries, app, db_session, seed_transactions
):
    """Тест 7: Пользователь не имеет отношения к транзакции."""
    # user_id=99999999 не существует в базе
    async with app.app_context():
        assert await check_user_in_sign("a" * 64) is False
