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
        response = await client.post(
            "/grist/webhook",
            headers={"X-Auth-Key": "wrong"},
            json=[{"UPDATE": True, "KEY": "TEST"}],
        )
        # It returns 200 "accepted" even if key is wrong according to code
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_grist_groups_invalid_key(client):
    with patch(
        "routers.grist.check_grist_key",
        new=AsyncMock(return_value={"status": "error", "message": "bad key"}),
    ):
        response = await client.get("/grist/groups/123", headers={"X-Auth-Key": "bad"})

    assert response.status_code == 403
    assert await response.get_json() == {"status": "error", "message": "bad key"}


@pytest.mark.asyncio
async def test_grist_sky_test_invalid_user_id(client):
    with patch(
        "routers.grist.check_grist_key",
        new=AsyncMock(return_value={"status": "success", "message": "OK", "data": {}}),
    ):
        response = await client.get(
            "/grist/sky_test/not-a-number", headers={"X-Auth-Key": "valid"}
        )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["status"] == "error"
    assert data["message"] == "Некорректный формат user_id"


@pytest.mark.asyncio
async def test_grist_webhook_table_authorized_updates_cache(client):
    with patch("routers.grist.config") as mock_config:
        mock_config.grist_income = "secret"
        with patch(
            "other.grist_cache.grist_cache.update_cache_by_webhook",
            new=AsyncMock(),
        ) as update_mock:
            response = await client.post(
                "/grist/webhook/EURMTL_assets",
                headers={"Authorization": "Bearer secret"},
            )

    assert response.status_code == 200
    assert await response.get_json() == {"status": "accepted"}
    update_mock.assert_awaited_once_with("EURMTL_assets")


@pytest.mark.asyncio
async def test_grist_webhook_authorized_processes_update_key(client):
    with patch("routers.grist.config") as mock_config:
        mock_config.grist_income = "secret"
        with patch("routers.grist._process_grist_key", new=AsyncMock()) as process_mock:
            response = await client.post(
                "/grist/webhook",
                headers={"X-Auth-Key": "secret"},
                json=[{"UPDATE": True, "KEY": "TEST", "id": 1}],
            )

    assert response.status_code == 200
    assert await response.get_json() == {"status": "accepted"}
    process_mock.assert_awaited_once_with(
        "TEST", {"UPDATE": True, "KEY": "TEST", "id": 1}
    )
