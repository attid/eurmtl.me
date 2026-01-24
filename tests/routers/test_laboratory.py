import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_lab_root(client):
    """Test /lab"""
    response = await client.get("/lab")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_lab_mtl_accounts(client):
    """Test /lab/mtl_accounts"""
    mock_accounts = [{"description": "Test", "account_id": "GABCDEFGHIJKLMNOPQRSTUVWXYZ123456"}]
    with patch("routers.laboratory.grist_manager.load_table_data", new=AsyncMock(return_value=mock_accounts)):
        response = await client.get("/lab/mtl_accounts")
        assert response.status_code == 200
        data = await response.get_json()
        assert any("Test" in k for k in data.keys())

@pytest.mark.asyncio
async def test_lab_sequence(client):
    """Test /lab/sequence/<account_id>"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.data = {'sequence': '100'}
    
    with patch("routers.laboratory.http_session_manager.get_web_request", new=AsyncMock(return_value=mock_response)):
        response = await client.get("/lab/sequence/GABC")
        assert response.status_code == 200
        data = await response.get_json()
        assert data['sequence'] == '101'

@pytest.mark.asyncio
async def test_lab_mtl_assets(client):
    """Test /lab/mtl_assets"""
    mock_assets = [{"code": "EURMTL", "issuer": "GABC"}]
    with patch("routers.laboratory.grist_manager.load_table_data", new=AsyncMock(return_value=mock_assets)):
        response = await client.get("/lab/mtl_assets")
        assert response.status_code == 200
        data = await response.get_json()
        assert "EURMTL-GABC" in data.values()

@pytest.mark.asyncio
async def test_lab_check_balance(client):
    """Test /lab/check_balance"""
    mock_account = {'balances': [{'asset_type': 'native', 'balance': '100.0'}]}
    
    with patch("routers.laboratory.Server") as MockServer:
        mock_server = MockServer.return_value
        mock_server.accounts.return_value.account_id.return_value.call = MagicMock(return_value=mock_account)
        
        response = await client.post("/lab/check_balance", json={
            "account_id": "GABC1234567890123456789012345678901234567890123456789012",
            "asset": "XLM"
        })
        assert response.status_code == 200
        data = await response.get_json()
        assert data['balance'] == '100.0'
