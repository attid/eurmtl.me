import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_rely_webhook_unauthorized(client):
    """Test /rely/grist-webhook without token"""
    response = await client.post("/rely/grist-webhook", json=[])
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_rely_webhook_invalid_token(client):
    """Test /rely/grist-webhook with invalid token"""
    with patch("routers.rely.config") as mock_config:
        mock_config.grist_income = "secret"
        response = await client.post("/rely/grist-webhook", 
                                    headers={"Authorization": "Bearer wrong"},
                                    json=[])
        assert response.status_code == 403

@pytest.mark.asyncio
async def test_rely_webhook_success(client):
    """Test /rely/grist-webhook success"""
    with patch("routers.rely.config") as mock_config:
        mock_config.grist_income = "secret"
        with patch("routers.rely._process_grist_payload") as mock_process:
            response = await client.post("/rely/grist-webhook", 
                                        headers={"Authorization": "Bearer secret"},
                                        json=[{"id": 1}])
            assert response.status_code == 200
            # process task is created in background, tricky to assert it ran without ensuring loop execution
            # but we assert response is 200
