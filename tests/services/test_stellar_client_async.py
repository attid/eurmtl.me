"""
Async tests for stellar_client.py functions.

This module contains async tests for:
- check_publish_state: Checking transaction status on Horizon
- check_user_weight: Checking user signer weight
- add_signer: Adding/updating signer in database
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import select
from datetime import datetime
from stellar_sdk import Keypair

from services.stellar_client import check_publish_state, check_user_weight, add_signer
from db.sql_models import Signers, Transactions
from other.grist_tools import User


# === TestCheckPublishState ===


class TestCheckPublishState:
    """Tests for check_publish_state function."""

    @pytest.mark.asyncio
    async def test_successful_transaction(self, app, db_session, seed_transactions):
        """
        Test successful transaction check (successful=True from Horizon).

        Verifies that:
        - Function returns state=1 for successful transaction
        - Date is correctly parsed from created_at field
        - Transaction state is updated to 2 in database
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch(
                "services.stellar_client.http_session_manager.get_web_request"
            ) as mock_get,
        ):
            # Mock Horizon API response for successful transaction
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.data = {
                "successful": True,
                "created_at": "2024-01-20T12:00:00Z",
            }
            mock_get.return_value = mock_response

            # Call function with transaction hash from seed data
            tx_hash = "a" * 64
            state, date = await check_publish_state(tx_hash)

            # Verify returned values
            assert state == 1
            assert date == "2024-01-20 12:00:00"

        # Verify database was updated (query after patch context to get fresh data)
        db_session.expire_all()  # Refresh session to see changes from other sessions
        result = await db_session.execute(
            select(Transactions).filter(Transactions.hash == tx_hash)
        )
        transaction = result.scalars().first()
        assert transaction.state == 2

    @pytest.mark.asyncio
    async def test_failed_transaction(self, app):
        """
        Test failed transaction check (successful=False from Horizon).

        Verifies that function returns state=10 for failed transactions.
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch(
                "services.stellar_client.http_session_manager.get_web_request"
            ) as mock_get,
        ):
            # Mock Horizon API response for failed transaction
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.data = {
                "successful": False,
                "created_at": "2024-01-20T12:00:00Z",
            }
            mock_get.return_value = mock_response

            tx_hash = "failed" + "0" * 58
            state, date = await check_publish_state(tx_hash)

            # Verify returned values
            assert state == 10
            assert date == "2024-01-20 12:00:00"

    @pytest.mark.asyncio
    async def test_not_found(self, app):
        """
        Test transaction not found (404 from Horizon).

        Verifies that function returns state=0 and 'Unknown' date
        when transaction is not found on Horizon.
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch(
                "services.stellar_client.http_session_manager.get_web_request"
            ) as mock_get,
        ):
            # Mock Horizon API 404 response
            mock_response = MagicMock()
            mock_response.status = 404
            mock_get.return_value = mock_response

            tx_hash = "notfound" + "0" * 56
            state, date = await check_publish_state(tx_hash)

            # Verify returned values
            assert state == 0
            assert date == "Unknown"

    @pytest.mark.asyncio
    async def test_network_error(self, app):
        """
        Test network error handling.

        Verifies that function gracefully handles network errors
        and returns state=0 with 'Unknown' date.
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch(
                "services.stellar_client.http_session_manager.get_web_request"
            ) as mock_get,
        ):
            # Mock network error
            mock_get.side_effect = Exception("Network error")

            tx_hash = "error" + "0" * 59
            state, date = await check_publish_state(tx_hash)

            # Verify returned values
            assert state == 0
            assert date == "Unknown"

    @pytest.mark.asyncio
    async def test_updates_transaction_state_in_db(
        self, app, db_session, seed_transactions
    ):
        """
        Test database state update for successful transaction.

        Verifies that:
        - Transaction state is updated from 0 to 2 in database
        - Only transactions with state != 2 are updated
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch(
                "services.stellar_client.http_session_manager.get_web_request"
            ) as mock_get,
        ):
            # Mock successful Horizon response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.data = {
                "successful": True,
                "created_at": "2024-01-20T12:00:00Z",
            }
            mock_get.return_value = mock_response

            # Use transaction from seed data (state=0)
            tx_hash = "a" * 64
            await check_publish_state(tx_hash)

            # Expire all to see changes from other sessions
            db_session.expire_all()

            # Verify state was updated in database
            result = await db_session.execute(
                select(Transactions).filter(Transactions.hash == tx_hash)
            )
            transaction = result.scalars().first()
            assert transaction is not None
            assert transaction.state == 2


# === TestCheckUserWeight ===


class TestCheckUserWeight:
    """Tests for check_user_weight function."""

    @pytest.mark.asyncio
    @patch("services.stellar_client.session", {"user_id": "84131737"})
    @patch("services.stellar_client.get_fund_signers")
    async def test_admin_user_has_weight(self, mock_get_fund_signers, app):
        """
        Test that admin user has correct weight.

        Verifies that function returns correct weight for user
        who is in the fund signers list.
        """
        # Mock fund signers data with admin user
        mock_get_fund_signers.return_value = {
            "signers": [
                {
                    "key": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                    "weight": 5,
                    "telegram_id": 84131737,
                },
                {"key": "GA" + "A" * 54, "weight": 3, "telegram_id": 12345678},
            ]
        }

        weight = await check_user_weight(need_flash=False)

        # Verify weight is correct
        assert weight == 5

    @pytest.mark.asyncio
    @patch("services.stellar_client.session", {"user_id": "99999"})
    @patch("services.stellar_client.get_fund_signers")
    async def test_user_not_a_signer(self, mock_get_fund_signers, app):
        """
        Test user not in signers list.

        Verifies that function returns weight=0 for user
        who is not in the fund signers list.
        """
        # Mock fund signers data without target user
        mock_get_fund_signers.return_value = {
            "signers": [
                {
                    "key": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                    "weight": 5,
                    "telegram_id": 84131737,
                },
                {"key": "GA" + "A" * 54, "weight": 3, "telegram_id": 12345678},
            ]
        }

        weight = await check_user_weight(need_flash=False)

        # Verify weight is 0
        assert weight == 0

    @pytest.mark.asyncio
    @patch("services.stellar_client.session", {})
    async def test_not_logged_in(self, app):
        """
        Test unauthorized user (not logged in).

        Verifies that function returns weight=0 for user
        without session (not logged in).
        """
        weight = await check_user_weight(need_flash=False)

        # Verify weight is 0
        assert weight == 0

    @pytest.mark.asyncio
    @patch("services.stellar_client.session", {"user_id": "12345"})
    @patch("services.stellar_client.get_fund_signers")
    async def test_fund_signers_empty(self, mock_get_fund_signers, app):
        """
        Test error getting fund account data.

        Verifies that function returns weight=0 when
        fund signers data is empty or None.
        """
        # Mock empty fund signers response
        mock_get_fund_signers.return_value = None

        weight = await check_user_weight(need_flash=False)

        # Verify weight is 0
        assert weight == 0


# === TestAddSigner ===


class TestAddSigner:
    """Tests for add_signer function."""

    @pytest.mark.asyncio
    async def test_add_new_signer(self, app, db_session):
        """
        Test adding a new signer to database.

        Verifies that:
        - New signer is added to database with correct data
        - Username from Grist is saved with @ prefix
        - Telegram ID is correctly saved
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        # Generate valid Stellar public key
        public_key = Keypair.random().public_key

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch("other.grist_cache.grist_cache.find_by_index") as mock_grist_cache,
            patch("other.grist_tools.grist_cash.get", return_value=None),
        ):
            # Mock Grist cache data
            mock_grist_cache.return_value = {
                "telegram_id": 55555,
                "username": "newuser",
                "account_id": public_key,
            }

            await add_signer(public_key)

            # Expire all to see changes from other sessions
            db_session.expire_all()

            # Verify signer was added to database
            result = await db_session.execute(
                select(Signers).filter(Signers.public_key == public_key)
            )
            signer = result.scalars().first()

            assert signer is not None
            assert signer.public_key == public_key
            assert signer.username == "@newuser"
            assert signer.tg_id == 55555

    @pytest.mark.asyncio
    async def test_add_signer_updates_existing(self, app, db_session, seed_signers):
        """
        Test updating existing signer in database.

        Verifies that:
        - Existing signer's username is updated
        - Telegram ID is updated
        - No duplicate signers are created
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch("other.grist_cache.grist_cache.find_by_index") as mock_grist_cache,
            patch("other.grist_tools.grist_cash.get", return_value=None),
        ):
            # Use @alice from seed_signers
            alice_pk = seed_signers[1].public_key  # GA + 'A' * 54

            # Mock updated Grist cache data
            mock_grist_cache.return_value = {
                "telegram_id": 99999999,
                "username": "alice_updated",
                "account_id": alice_pk,
            }

            await add_signer(alice_pk)

            # Expire all to see changes from other sessions
            db_session.expire_all()

            # Verify signer was updated
            result = await db_session.execute(
                select(Signers).filter(Signers.public_key == alice_pk)
            )
            signer = result.scalars().first()

            assert signer is not None
            assert signer.username == "@alice_updated"
            assert signer.tg_id == 99999999

            # Verify no duplicates were created
            all_result = await db_session.execute(
                select(Signers).filter(Signers.public_key == alice_pk)
            )
            all_signers = all_result.scalars().all()
            assert len(all_signers) == 1

    @pytest.mark.asyncio
    async def test_add_signer_without_grist_data(self, app, db_session):
        """
        Test adding signer without Grist data.

        Verifies that:
        - Signer is added with default username 'FaceLess'
        - Telegram ID is set to None
        - Signature hint is correctly generated
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        # Generate valid Stellar public key
        public_key = Keypair.random().public_key

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch("other.grist_cache.grist_cache.find_by_index", return_value=None),
            patch("other.grist_tools.grist_cash.get", return_value=None),
        ):
            await add_signer(public_key)

            # Expire all to see changes from other sessions
            db_session.expire_all()

            # Verify signer was added with default values
            result = await db_session.execute(
                select(Signers).filter(Signers.public_key == public_key)
            )
            signer = result.scalars().first()

            assert signer is not None
            assert signer.username == "FaceLess"
            assert signer.tg_id is None
            assert signer.signature_hint is not None

    @pytest.mark.asyncio
    async def test_add_signer_with_username_without_at(self, app, db_session):
        """
        Test adding signer with username without @ prefix.

        Verifies that:
        - Username without @ is automatically prefixed with @
        - Username is saved correctly in database
        """
        # Create mock app to replace current_app
        mock_app = MagicMock()
        mock_app.db_pool = app.db_pool

        # Generate valid Stellar public key
        public_key = Keypair.random().public_key

        with (
            patch("services.stellar_client.current_app", mock_app),
            patch("other.grist_cache.grist_cache.find_by_index") as mock_grist_cache,
            patch("other.grist_tools.grist_cash.get", return_value=None),
        ):
            # Mock Grist cache data with username without @
            mock_grist_cache.return_value = {
                "telegram_id": 77777,
                "username": "alice",  # without @
                "account_id": public_key,
            }

            await add_signer(public_key)

            # Expire all to see changes from other sessions
            db_session.expire_all()

            # Verify username has @ prefix
            result = await db_session.execute(
                select(Signers).filter(Signers.public_key == public_key)
            )
            signer = result.scalars().first()

            assert signer is not None
            assert signer.username == "@alice"
            assert signer.tg_id == 77777
