import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.transaction_service import TransactionService
from db.sql_models import Transactions, Signers, Signatures

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
    mock_tx = Transactions(hash="hash1", body="body1", add_dt=MagicMock(), description="desc")
    mock_tx.add_dt.isoformat.return_value = "2023-01-01"
    
    transaction_service.repo.get_signer_by_public_key = AsyncMock(return_value=mock_signer)
    transaction_service.repo.get_pending_for_signer = AsyncMock(return_value=[mock_tx])
    
    # Execute
    result = await transaction_service.get_pending_transactions_for_signer("GABC")
    
    # Verify
    assert len(result) == 1
    assert result[0]['hash'] == "hash1"
    assert result[0]['description'] == "desc"

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
