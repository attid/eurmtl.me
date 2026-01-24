import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_grist_tg_info(client):
    """Test /grist/tg_info.html"""
    response = await client.get("/grist/tg_info.html")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_grist_menu_unauthorized(client):
    """Test /grist/menu without key"""
    response = await client.get("/grist/menu")
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_grist_menu_authorized(client):
    """Test /grist/menu with valid key"""
    mock_check = {"status": "success", "message": "OK", "data": {"user_id": 123}}
    with patch("routers.grist.check_grist_key", new=AsyncMock(return_value=mock_check)):
        response = await client.get("/grist/menu", headers={"X-Auth-Key": "valid_key"})
        assert response.status_code == 200
        data = await response.get_json()
        assert "buttons" in data

@pytest.mark.asyncio
async def test_grist_webhook_unauthorized(client):
    """Test /grist/webhook with invalid key"""
    # Mock config.grist_income
    with patch("routers.grist.config") as mock_config:
        mock_config.grist_income = "secret"
        response = await client.post("/grist/webhook", 
                                    headers={"X-Auth-Key": "wrong"},
                                    json=[{"UPDATE": True, "KEY": "TEST"}])
        # It returns 200 "accepted" even if key is wrong according to code
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "accepted"
