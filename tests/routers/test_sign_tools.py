import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_sign_tools_add_get(client):
    """Test GET /sign_tools"""
    response = await client.get("/sign_tools")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_sign_tools_add_post_success(client):
    """Test POST /sign_tools with success"""
    with patch("routers.sign_tools.add_transaction", new=AsyncMock(return_value=(True, "hash123"))):
        response = await client.post("/sign_tools", form={
            "xdr": "AAAA...", 
            "description": "Test Transaction"
        })
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/sign_tools/hash123")

@pytest.mark.asyncio
async def test_sign_tools_add_post_fail(client):
    """Test POST /sign_tools with invalid input"""
    response = await client.post("/sign_tools", form={"xdr": ""})
    # Should flash error and render template (status 200)
    assert response.status_code == 200
    assert "Transaction XDR is required" in await response.get_data(as_text=True)

@pytest.mark.asyncio
async def test_sign_tools_show_transaction(client):
    """Test GET /sign_tools/<hash>"""
    mock_details = {
        "transaction": MagicMock(),
        "transaction_env": MagicMock(),
        "tx_description": "desc",
        "signatures": [],
        "signers_table": [],
        "alert": False,
        "admin_weight": 0,
        "publish_state": (0, "Unknown"),
        "user_id": 0
    }
    
    with patch("routers.sign_tools.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.get_transaction_details = AsyncMock(return_value=mock_details)
        
        response = await client.get("/sign_tools/0000000000000000000000000000000000000000000000000000000000000000")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_sign_tools_show_transaction_not_found(client):
    """Test GET /sign_tools/<hash> not found"""
    with patch("routers.sign_tools.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.get_transaction_details = AsyncMock(return_value=None)
        
        response = await client.get("/sign_tools/0000000000000000000000000000000000000000000000000000000000000000")
        assert "Transaction not exist" in await response.get_data(as_text=True)

@pytest.mark.asyncio
async def test_sign_tools_list(client):
    """Test GET /sign_all"""
    with patch("routers.sign_tools.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.search_transactions = AsyncMock(return_value=[])
        
        response = await client.get("/sign_all")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_sign_tools_decode(client):
    """Test GET /decode/<hash>"""
    mock_tx = MagicMock()
    mock_tx.body = "AAAA..."
    
    with patch("routers.sign_tools.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.get_transaction_by_hash = AsyncMock(return_value=mock_tx)
        
        with patch("routers.sign_tools.decode_xdr_to_text", new=AsyncMock(return_value=["Line 1", "Line 2"])):
            response = await client.get("/decode/0000000000000000000000000000000000000000000000000000000000000000")
            assert response.status_code == 200
            data = await response.get_data(as_text=True)
            assert "Line 1" in data
