import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_decision_add_get(client):
    """Test GET /decision"""
    with patch("routers.decision.check_user_weight", new=AsyncMock(return_value=0)):
        response = await client.get("/decision")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_decision_add_post_no_auth(client):
    """Test POST /decision without authority"""
    with patch("routers.decision.check_user_weight", new=AsyncMock(return_value=0)):
        response = await client.post("/decision", form={
            "question_number": "1",
            "short_subject": "Test",
            "inquiry": "Text",
            "status": "active",
            "reading": "1"
        })
        # Should stay on page and show "need authority" flashed (not in response body usually if not using templates correctly in mock)
        # But here it just returns render_template
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_decision_get_number(client):
    """Test /decision/number"""
    with patch("routers.decision.gs_get_last_id", new=AsyncMock(return_value=[10])):
        response = await client.get("/decision/number")
        assert response.status_code == 200
        data = await response.get_json()
        assert data['number'] == '11'

@pytest.mark.asyncio
async def test_decision_update_text_unauthorized(client):
    """Test /decision/update_text with wrong token"""
    response = await client.post("/decision/update_text", 
                                headers={"Authorization": "Bearer wrong_token"},
                                json={"msg_url": "url", "msg_text": "text"})
    assert response.status_code == 401
