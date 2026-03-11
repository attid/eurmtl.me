import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select
from services.transaction_service import TransactionService
from db.sql_models import Transactions, Signers, Signatures, Alerts
from stellar_sdk.exceptions import BadSignatureError


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    return session


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
async def test_get_transaction_by_hash_uses_uuid_branch(transaction_service):
    transaction_service.repo.get_by_uuid = AsyncMock(return_value="tx-by-uuid")

    result = await transaction_service.get_transaction_by_hash("short-uuid")

    assert result == "tx-by-uuid"
    transaction_service.repo.get_by_uuid.assert_awaited_once_with("short-uuid")


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


@pytest.mark.asyncio
async def test_update_signature_visibility_returns_false_when_signature_missing(
    transaction_service, mock_session
):
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_session.execute.return_value = mock_result

    result = await transaction_service.update_signature_visibility(999, True)

    assert result is False
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_sign_transaction_from_xdr_rejects_bad_xdr(transaction_service):
    result = await transaction_service.sign_transaction_from_xdr("not-xdr")

    assert result["SUCCESS"] is False
    assert result["MESSAGES"] == ["BAD xdr. Can`t load"]


@pytest.mark.asyncio
async def test_sign_transaction_from_xdr_returns_not_found_for_unknown_transaction(
    transaction_service,
):
    with patch("services.transaction_service.TransactionEnvelope") as envelope_cls:
        envelope = MagicMock()
        envelope.hash_hex.return_value = "a" * 64
        envelope_cls.from_xdr.return_value = envelope
        transaction_service.repo.get_by_hash = AsyncMock(return_value=None)

        result = await transaction_service.sign_transaction_from_xdr("AAAA")

    assert result["SUCCESS"] is False
    assert result["hash"] == "a" * 64
    assert result["MESSAGES"] == ["Transaction not found"]


@pytest.mark.asyncio
async def test_sign_transaction_from_xdr_returns_error_for_bad_transaction_json(
    transaction_service,
):
    with patch("services.transaction_service.TransactionEnvelope") as envelope_cls:
        envelope = MagicMock()
        envelope.hash_hex.return_value = "a" * 64
        envelope.signatures = []
        envelope_cls.from_xdr.return_value = envelope

        transaction = Transactions(hash="a" * 64, body="AAAA", json="{bad-json")
        transaction_service.repo.get_by_hash = AsyncMock(return_value=transaction)

        result = await transaction_service.sign_transaction_from_xdr("AAAA")

    assert result["SUCCESS"] is False
    assert result["MESSAGES"] == ["Can`t load json"]


@pytest.mark.asyncio
async def test_create_transaction_uri_returns_none_when_transaction_missing(
    transaction_service,
):
    transaction_service.repo.get_by_hash = AsyncMock(return_value=None)

    result = await transaction_service.create_transaction_uri("a" * 64)

    assert result is None


@pytest.mark.asyncio
async def test_add_or_remove_alert_returns_error_on_session_failure(
    transaction_service, mock_session
):
    mock_session.execute.side_effect = RuntimeError("db failed")

    result = await transaction_service.add_or_remove_alert("hash", 123)

    assert result["success"] is False
    assert "db failed" in result["message"]


def _result_with(first=None, all_items=None):
    result = MagicMock()
    result.scalars().first.return_value = first
    result.scalars().all.return_value = all_items or []
    return result


def _signature_mock(hint="hint1", xdr_value="sig-xdr", signature_bytes=b"sig"):
    signature = MagicMock()
    signature.signature_hint.hex.return_value = hint
    signature.to_xdr_object.return_value.to_xdr.return_value = xdr_value
    signature.signature = signature_bytes
    return signature


@pytest.mark.asyncio
async def test_get_transaction_details_happy_path(transaction_service, mock_session):
    transaction = Transactions(
        hash="a" * 64,
        body="AAAA",
        json='{"GA1":{"threshold":2,"signers":[["GA1",2,"hint1"]]}}',
        description="Decision text",
        uuid="u" * 32,
    )
    db_signer = Signers(id=1, public_key="GA1", tg_id=100)
    db_signature = Signatures(
        id=1,
        signer_id=1,
        signature_xdr="sig-xdr",
        transaction_hash=transaction.hash,
    )
    db_signature.add_dt = MagicMock()

    transaction_service.get_transaction_by_hash = AsyncMock(return_value=transaction)
    transaction_service.repo.get_signature_by_signer_public_key = AsyncMock(
        return_value=None
    )
    transaction_service.repo.get_signer_by_public_key = AsyncMock(
        return_value=db_signer
    )
    transaction_service.repo.get_latest_signature_by_signer = AsyncMock(
        return_value=None
    )
    transaction_service.repo.get_latest_signature_for_source = AsyncMock(
        return_value=None
    )
    transaction_service.repo.get_all_signatures_for_transaction = AsyncMock(
        return_value=[db_signature]
    )
    mock_session.execute.side_effect = [
        _result_with(first=Alerts(id=1, tg_id=100, transaction_hash=transaction.hash)),
        _result_with(all_items=[db_signer]),
    ]

    with (
        patch(
            "services.transaction_service.check_user_in_sign",
            AsyncMock(return_value=True),
        ),
        patch(
            "services.transaction_service.check_publish_state",
            AsyncMock(return_value=(1, "date")),
        ),
        patch(
            "services.transaction_service.load_users_from_grist",
            AsyncMock(
                side_effect=[
                    {"GA1": MagicMock(username="alice", telegram_id=100)},
                    {"GA1": MagicMock(username="alice", telegram_id=100)},
                ]
            ),
        ),
        patch("services.transaction_service.TransactionEnvelope.from_xdr") as from_xdr,
    ):
        envelope = MagicMock()
        envelope.signatures = []
        envelope.to_xdr.return_value = "full-xdr"
        from_xdr.return_value = envelope

        result = await transaction_service.get_transaction_details(
            transaction.hash, 100
        )

    assert result["admin_weight"] == 2
    assert result["alert"].tg_id == 100
    assert result["tx_full"] == "full-xdr"
    assert result["publish_state"] == (1, "date")
    assert result["signers_table"][0]["threshold"] == 2
    assert result["signers_table"][0]["signers"][0][1] == "alice"
    assert result["signatures"][0][2] == "alice"


@pytest.mark.asyncio
async def test_get_transaction_details_returns_bad_xdr_on_invalid_json(
    transaction_service,
):
    transaction = Transactions(
        hash="a" * 64, body="AAAA", json="{bad", description="Broken"
    )
    transaction_service.get_transaction_by_hash = AsyncMock(return_value=transaction)

    with patch(
        "services.transaction_service.check_user_in_sign", AsyncMock(return_value=False)
    ):
        result = await transaction_service.get_transaction_details(transaction.hash, 0)

    assert result["error"] == "BAD xdr. Can`t load"


@pytest.mark.asyncio
async def test_sign_transaction_from_xdr_handles_existing_signature(
    transaction_service, mock_session
):
    signature = _signature_mock()
    envelope = MagicMock()
    envelope.hash_hex.return_value = "a" * 64
    envelope.signatures = [signature]
    envelope.hash.return_value = b"hash"

    transaction = Transactions(
        hash="a" * 64,
        body="AAAA",
        json='{"GA1":{"signers":[["GA1",1,"hint1"]]}}',
        description="Tx",
    )
    db_signer = Signers(id=1, public_key="GA1", signature_hint="hint1")
    mock_session.execute.side_effect = [
        _result_with(all_items=[db_signer]),
        _result_with(first=object()),
    ]
    transaction_service.repo.get_by_hash = AsyncMock(return_value=transaction)

    with (
        patch(
            "services.transaction_service.TransactionEnvelope.from_xdr",
            return_value=envelope,
        ),
        patch(
            "services.transaction_service.load_users_from_grist",
            AsyncMock(return_value={"GA1": MagicMock(username="alice")}),
        ),
    ):
        result = await transaction_service.sign_transaction_from_xdr("AAAA")

    assert result["MESSAGES"] == ["Can`t add alice. Already was added."]


@pytest.mark.asyncio
async def test_sign_transaction_from_xdr_rejects_unknown_signature_hint(
    transaction_service, mock_session
):
    signature = _signature_mock(hint="missing")
    envelope = MagicMock()
    envelope.hash_hex.return_value = "a" * 64
    envelope.signatures = [signature]
    envelope.hash.return_value = b"hash"

    transaction = Transactions(
        hash="a" * 64,
        body="AAAA",
        json='{"GA1":{"signers":[["GA1",1,"hint1"]]}}',
        description="Tx",
    )
    db_signer = Signers(id=1, public_key="GA1", signature_hint="hint1")
    mock_session.execute.side_effect = [
        _result_with(all_items=[db_signer]),
        _result_with(first=None),
    ]
    transaction_service.repo.get_by_hash = AsyncMock(return_value=transaction)

    with (
        patch(
            "services.transaction_service.TransactionEnvelope.from_xdr",
            return_value=envelope,
        ),
        patch(
            "services.transaction_service.load_users_from_grist",
            AsyncMock(return_value={"GA1": MagicMock(username="alice")}),
        ),
    ):
        result = await transaction_service.sign_transaction_from_xdr("AAAA")

    assert result["MESSAGES"] == ["Bad signature. missing not found"]


@pytest.mark.asyncio
async def test_sign_transaction_from_xdr_rejects_unverifiable_signature(
    transaction_service, mock_session
):
    signature = _signature_mock()
    envelope = MagicMock()
    envelope.hash_hex.return_value = "a" * 64
    envelope.signatures = [signature]
    envelope.hash.return_value = b"hash"

    transaction = Transactions(
        hash="a" * 64,
        body="AAAA",
        json='{"GA1":{"signers":[["GA1",1,"hint1"]]}}',
        description="Tx",
    )
    db_signer = Signers(id=1, public_key="GA1", signature_hint="hint1")
    mock_session.execute.side_effect = [
        _result_with(all_items=[db_signer]),
        _result_with(first=None),
    ]
    transaction_service.repo.get_by_hash = AsyncMock(return_value=transaction)

    with (
        patch(
            "services.transaction_service.TransactionEnvelope.from_xdr",
            return_value=envelope,
        ),
        patch(
            "services.transaction_service.load_users_from_grist",
            AsyncMock(return_value={"GA1": MagicMock(username="alice")}),
        ),
        patch(
            "services.transaction_service.Keypair.from_public_key"
        ) as from_public_key,
    ):
        from_public_key.return_value.verify.side_effect = BadSignatureError("bad")
        result = await transaction_service.sign_transaction_from_xdr("AAAA")

    assert result["MESSAGES"] == ["Bad signature. hint1 not verify"]


@pytest.mark.asyncio
async def test_sign_transaction_from_xdr_adds_valid_signature_and_notifies(
    transaction_service, mock_session
):
    signature = _signature_mock()
    envelope = MagicMock()
    envelope.hash_hex.return_value = "a" * 64
    envelope.signatures = [signature]
    envelope.hash.return_value = b"hash"

    transaction = Transactions(
        hash="a" * 64,
        body="AAAA",
        json='{"GA1":{"signers":[["GA1",1,"hint1"]]}}',
        description="Tx",
    )
    db_signer = Signers(id=1, public_key="GA1", signature_hint="hint1")
    mock_session.execute.side_effect = [
        _result_with(all_items=[db_signer]),
        _result_with(first=None),
    ]
    transaction_service.repo.get_by_hash = AsyncMock(return_value=transaction)
    transaction_service.alert_signers_notify = AsyncMock()

    with (
        patch(
            "services.transaction_service.TransactionEnvelope.from_xdr",
            return_value=envelope,
        ),
        patch(
            "services.transaction_service.load_users_from_grist",
            AsyncMock(return_value={"GA1": MagicMock(username="alice")}),
        ),
        patch(
            "services.transaction_service.Keypair.from_public_key"
        ) as from_public_key,
    ):
        from_public_key.return_value.verify.return_value = None
        result = await transaction_service.sign_transaction_from_xdr("AAAA")

    assert result["SUCCESS"] is True
    assert result["MESSAGES"] == ["Added signature from alice"]
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()
    transaction_service.alert_signers_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_transaction_authorizes_owner_and_reports_result(
    transaction_service,
):
    transaction = Transactions(hash="a" * 64, owner_id=123)
    transaction_service.get_transaction_by_hash = AsyncMock(return_value=transaction)

    with (
        patch(
            "services.transaction_service.check_user_in_sign",
            AsyncMock(return_value=False),
        ),
        patch(
            "services.transaction_service.update_transaction_sources",
            AsyncMock(return_value=True),
        ),
    ):
        ok, message = await transaction_service.refresh_transaction(
            transaction.hash, 123
        )

    assert ok is True
    assert "успешно обновлена" in message


@pytest.mark.asyncio
async def test_refresh_transaction_rejects_without_permissions(transaction_service):
    transaction = Transactions(hash="a" * 64, owner_id=999)
    transaction_service.get_transaction_by_hash = AsyncMock(return_value=transaction)

    with patch(
        "services.transaction_service.check_user_in_sign", AsyncMock(return_value=False)
    ):
        ok, message = await transaction_service.refresh_transaction(
            transaction.hash, 123
        )

    assert ok is False
    assert "нет прав" in message


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
