import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from services.transaction_service import TransactionService
from db.sql_models import Transactions, Signers, Signatures, Alerts


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def transaction_service(mock_session):
    return TransactionService(mock_session)


@pytest.mark.asyncio
async def test_get_transaction_details_not_found(transaction_service):
    transaction_service.repo.get_by_hash = AsyncMock(return_value=None)
    transaction_service.repo.get_by_uuid = AsyncMock(return_value=None)

    result = await transaction_service.get_transaction_details("nonexistent", 0)
    assert result is None


@pytest.mark.asyncio
async def test_get_pending_transactions(transaction_service):
    # Setup
    mock_signer = Signers(id=1, public_key="GABC")
    mock_tx = Transactions(
        hash="hash1", body="body1", add_dt=MagicMock(), description="desc"
    )
    mock_tx.add_dt.isoformat.return_value = "2023-01-01"

    transaction_service.repo.get_signer_by_public_key = AsyncMock(
        return_value=mock_signer
    )
    transaction_service.repo.get_pending_for_signer = AsyncMock(return_value=[mock_tx])

    # Execute
    result = await transaction_service.get_pending_transactions_for_signer("GABC")

    # Verify
    assert len(result) == 1
    assert result[0]["hash"] == "hash1"
    assert result[0]["description"] == "desc"


@pytest.mark.asyncio
async def test_update_signature_visibility(transaction_service, mock_session):
    # Setup
    mock_result = MagicMock()
    mock_sig = Signatures(id=1, hidden=0)
    mock_result.scalars().first.return_value = mock_sig
    mock_session.execute.return_value = mock_result

    # Execute
    await transaction_service.update_signature_visibility(1, True)

    # Verify
    assert mock_sig.hidden == 1
    mock_session.commit.assert_called_once()


# ===== New tests with real SQLite DB =====


class TestSearchTransactions:
    """Tests for search_transactions() with real database."""

    @pytest.mark.asyncio
    async def test_search_by_state_new(self, app, db_session, seed_transactions):
        """Test searching transactions by state=0 (new)."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Search for new transactions (state=0)
            results = await service.search_transactions(
                filters={"status": 0}, limit=10, offset=0
            )

            # Verify: should find transaction 'a'*64
            assert len(results) == 1
            assert results[0].hash == "a" * 64
            assert results[0].state == 0

    @pytest.mark.asyncio
    async def test_search_by_state_sent(self, app, db_session, seed_transactions):
        """Test searching transactions by state=2 (sent)."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Search for sent transactions (state=2)
            results = await service.search_transactions(
                filters={"status": 2}, limit=10, offset=0
            )

            # Verify: should find transaction 'c'*64
            assert len(results) == 1
            assert results[0].hash == "c" * 64
            assert results[0].state == 2

    @pytest.mark.asyncio
    async def test_search_by_owner_id(self, app, db_session, seed_transactions):
        """Test searching transactions by owner_id."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Search for @alice's transactions (owner_id=12345678)
            results = await service.search_transactions(
                filters={"owner_id": 12345678}, limit=10, offset=0
            )

            # Verify: should find transaction 'a'*64
            # Note: search_transactions returns selected fields, not full objects
            assert len(results) == 1
            assert results[0].hash == "a" * 64

    @pytest.mark.asyncio
    async def test_search_with_combined_filters(
        self, app, db_session, seed_transactions
    ):
        """Test searching with multiple filters (status + owner_id)."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Search for @bob's transactions with state=1
            results = await service.search_transactions(
                filters={"status": 1, "owner_id": 23456789}, limit=10, offset=0
            )

            # Verify: should find transaction 'b'*64
            # Note: search_transactions returns selected fields, not full objects
            assert len(results) == 1
            assert results[0].hash == "b" * 64
            assert results[0].state == 1

    @pytest.mark.asyncio
    async def test_search_with_limit_offset(self, app, db_session, seed_transactions):
        """Test searching with limit and offset pagination."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Search all transactions with limit=1, offset=0
            results_page1 = await service.search_transactions(
                filters={}, limit=1, offset=0
            )

            # Search all transactions with limit=1, offset=1
            results_page2 = await service.search_transactions(
                filters={}, limit=1, offset=1
            )

            # Verify: should get different transactions
            assert len(results_page1) == 1
            assert len(results_page2) == 1
            assert results_page1[0].hash != results_page2[0].hash


class TestAddOrRemoveAlert:
    """Tests for add_or_remove_alert() with real database."""

    @pytest.mark.asyncio
    async def test_add_new_alert(self, app, db_session, seed_transactions):
        """Test adding a new alert subscription."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Add alert for transaction 'c'*64 for user 55555
            result = await service.add_or_remove_alert(tr_hash="c" * 64, tg_id=55555)

            # Verify result
            assert result["success"] is True
            assert result["icon"] == "ti-bell-ringing"
            assert "added" in result["message"].lower()

            # Verify alert was added to database
            db_result = await db_session.execute(
                select(Alerts).filter(
                    Alerts.transaction_hash == "c" * 64, Alerts.tg_id == 55555
                )
            )
            alert = db_result.scalars().first()
            assert alert is not None
            assert alert.tg_id == 55555

    @pytest.mark.asyncio
    async def test_remove_existing_alert(self, app, db_session, seed_alerts):
        """Test removing an existing alert subscription."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Remove alert for @alice (tg_id=12345678) on transaction 'a'*64
            result = await service.add_or_remove_alert(tr_hash="a" * 64, tg_id=12345678)

            # Verify result
            assert result["success"] is True
            assert result["icon"] == "ti-bell-off"
            assert "removed" in result["message"].lower()

            # Verify alert was removed from database
            db_result = await db_session.execute(
                select(Alerts).filter(
                    Alerts.transaction_hash == "a" * 64, Alerts.tg_id == 12345678
                )
            )
            alert = db_result.scalars().first()
            assert alert is None


class TestUpdateSignatureVisibility:
    """Tests for update_signature_visibility() with real database."""

    @pytest.mark.asyncio
    async def test_hide_signature(self, app, db_session, seed_signatures):
        """Test hiding a visible signature."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Hide signature id=1 (@alice's signature, currently visible)
            success = await service.update_signature_visibility(
                signature_id=1, hide=True
            )

            # Verify success
            assert success is True

            # Verify signature is hidden in database
            db_session.expire_all()
            db_result = await db_session.execute(
                select(Signatures).filter(Signatures.id == 1)
            )
            signature = db_result.scalars().first()
            assert signature.hidden == 1

    @pytest.mark.asyncio
    async def test_show_signature(self, app, db_session, seed_signatures):
        """Test showing a hidden signature."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Show signature id=2 (@bob's hidden signature)
            success = await service.update_signature_visibility(
                signature_id=2, hide=False
            )

            # Verify success
            assert success is True

            # Verify signature is visible in database
            db_session.expire_all()
            db_result = await db_session.execute(
                select(Signatures).filter(Signatures.id == 2)
            )
            signature = db_result.scalars().first()
            assert signature.hidden == 0


class TestRefreshTransaction:
    """Tests for refresh_transaction() with real database."""

    @pytest.mark.asyncio
    @patch("services.transaction_service.check_user_in_sign")
    @patch("services.transaction_service.update_transaction_sources")
    async def test_refresh_as_admin(
        self, mock_update_sources, mock_check_user, app, db_session, seed_transactions
    ):
        """Test successful refresh with admin privileges."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Mock admin user
            mock_check_user.return_value = True  # User is admin
            mock_update_sources.return_value = True  # Update successful

            # Refresh transaction 'a'*64 as admin
            success, message = await service.refresh_transaction(
                tr_hash="a" * 64,
                user_id=84131737,  # admin
            )

            # Verify success
            assert success is True
            assert "успешно обновлена" in message.lower()

            # Verify update_transaction_sources was called
            mock_update_sources.assert_called_once()

    @pytest.mark.asyncio
    @patch("services.transaction_service.check_user_in_sign")
    @patch("services.transaction_service.update_transaction_sources")
    async def test_refresh_as_owner(
        self, mock_update_sources, mock_check_user, app, db_session, seed_transactions
    ):
        """Test successful refresh as transaction owner."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Mock non-admin user but owner
            mock_check_user.return_value = False  # Not admin
            mock_update_sources.return_value = True  # Update successful

            # Refresh transaction 'a'*64 as owner @alice (owner_id=12345678)
            success, message = await service.refresh_transaction(
                tr_hash="a" * 64,
                user_id=12345678,  # @alice (owner)
            )

            # Verify success
            assert success is True
            assert "успешно обновлена" in message.lower()

    @pytest.mark.asyncio
    @patch("services.transaction_service.check_user_in_sign")
    async def test_refresh_without_permissions(
        self, mock_check_user, app, db_session, seed_transactions
    ):
        """Test refresh failure without proper permissions."""
        async with app.app_context():
            service = TransactionService(db_session)

            # Mock non-admin, non-owner user
            mock_check_user.return_value = False  # Not admin

            # Try to refresh transaction 'a'*64 as @bob (not owner)
            success, message = await service.refresh_transaction(
                tr_hash="a" * 64,
                user_id=23456789,  # @bob (not owner)
            )

            # Verify failure
            assert success is False
            assert "нет прав" in message.lower()
