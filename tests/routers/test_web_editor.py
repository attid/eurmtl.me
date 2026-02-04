import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_web_editor_get_unauthorized(client):
    """Test /WebEditor without admin rights"""
    with patch("routers.web_editor.is_bot_admin", new=AsyncMock(return_value=False)):
        response = await client.get("/WebEditor?tgWebAppStartParam=123_456")
        assert response.status_code == 403

@pytest.mark.asyncio
async def test_web_editor_get_authorized_not_found(client, app):
    """Test /WebEditor with admin rights but message not in DB"""
    with patch("routers.web_editor.is_bot_admin", new=AsyncMock(return_value=True)):
        with patch("routers.web_editor.skynet_bot.edit_message_text", new=AsyncMock()) as mock_edit:
            response = await client.get("/WebEditor?tgWebAppStartParam=123_456")
            # It tries to edit message and then render template
            assert response.status_code == 200
            assert "Your text here..." in await response.get_data(as_text=True)

@pytest.mark.asyncio
async def test_web_editor_action_no_data(client):
    """Test /WebEditorAction missing data"""
    response = await client.post("/WebEditorAction", json={})
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_join_captcha_get(client):
    """Test /JoinCaptcha GET"""
    response = await client.get("/JoinCaptcha?tgWebAppStartParam=123_1")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_join_captcha_post_success(client):
    """Test /JoinCaptcha POST success"""
    with patch("routers.web_editor.user_has_edit_permissions", return_value=123):
        with patch("routers.web_editor.check_response_captcha", new=AsyncMock(return_value=True)):
            with patch("routers.web_editor.skynet_bot.approve_chat_join_request", new=AsyncMock()) as mock_approve:
                response = await client.post("/JoinCaptcha", json={
                    "initData": "data",
                    "chatId": 123,
                    "token": "token",
                    "v2": "false"
                })
                assert response.status_code == 200
                mock_approve.assert_called_once()
