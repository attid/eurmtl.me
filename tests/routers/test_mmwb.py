import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_mmwb_manage_data_get(client):
    """Test GET /ManageData"""
    mock_account = {'data': {'test_key': 'dGVzdF92YWx1ZQ=='}} # base64 for test_value
    with patch("routers.mmwb.get_account_fresh", new=AsyncMock(return_value=mock_account)):
        response = await client.get("/ManageData?account_id=GABC")
        assert response.status_code == 200
        assert "test_key" in await response.get_data(as_text=True)

@pytest.mark.asyncio
async def test_mmwb_manage_data_no_account(client):
    """Test GET /ManageData without account_id"""
    response = await client.get("/ManageData")
    assert response.status_code == 400
    assert "Параметры не найдены" in await response.get_data(as_text=True)

@pytest.mark.asyncio
async def test_mmwb_manage_data_action_unauthorized(client):
    """Test POST /ManageDataAction with invalid initData"""
    with patch("routers.mmwb.check_response_webapp", return_value=False):
        response = await client.post("/ManageDataAction", json={
            "user_id": "123",
            "message_id": "456",
            "initData": "some_data"
        })
        assert response.status_code == 403
        data = await response.get_json()
        assert data['error'] == 'Нет прав на редактирование'
