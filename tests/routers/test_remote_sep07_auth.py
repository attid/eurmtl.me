import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_sep07_auth_test(client):
    """Test /remote/sep07/auth/test"""
    response = await client.get("/remote/sep07/auth/test")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_sep07_auth_init(client):
    """Test /remote/sep07/auth/init"""
    with patch("routers.remote_sep07_auth.create_sep7_auth_transaction", new=AsyncMock(return_value="web+stellar:tx...")):
        with patch("routers.remote_sep07_auth.create_beautiful_code"):
            response = await client.post("/remote/sep07/auth/init", json={"domain": "example.com", "nonce": "123"})
            assert response.status_code == 200
            data = await response.get_json()
            assert "uri" in data

@pytest.mark.asyncio
async def test_sep07_auth_status_not_found(client):
    """Test /remote/sep07/auth/status/<nonce>/<salt>"""
    response = await client.get("/remote/sep07/auth/status/123/salt")
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_sep07_auth_callback(client):
    """Test /remote/sep07/auth/callback"""
    # Need to setup nonce in store first or mock it.
    # It's easier to mock process_xdr_transaction but we also need nonce in store.
    # Let's just test invalid case first.
    response = await client.post("/remote/sep07/auth/callback", form={"xdr": "AAAAAA=="})
    assert response.status_code == 400 # Nonce not found or error
