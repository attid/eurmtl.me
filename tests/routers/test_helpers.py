import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_helpers_seller_get(client):
    """Test GET /seller/<account_id>"""
    response = await client.get("/seller/GABCDEFGHIJKLMNOPQRSTUVWXYZ12345678901234567890123456")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_helpers_seller_post(client):
    """Test POST /seller/<account_id>"""
    valid_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    with patch("routers.helpers.create_beautiful_code") as mock_qr:
        response = await client.post(f"/seller/{valid_key}", form={
            "sale_sum": "100",
            "memo_text": "Test"
        })
        assert response.status_code == 200
        mock_qr.assert_called_once()

@pytest.mark.asyncio
async def test_helpers_asset_get(client):
    """Test GET /asset/<asset_code>"""
    mock_asset = {"code": "EURMTL", "issuer": "GABC"}
    with patch("routers.helpers.get_grist_asset_by_code", new=AsyncMock(return_value=mock_asset)):
        with patch("routers.helpers.add_trust_line_uri", return_value="web+stellar:tx..."):
            with patch("routers.helpers.create_beautiful_code"):
                with patch("os.path.exists", return_value=False):
                    response = await client.get("/asset/EURMTL")
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_helpers_uri_get(client):
    """Test GET /uri"""
    response = await client.get("/uri")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_helpers_generate_get(client):
    """Test GET /generate"""
    response = await client.get("/generate")
    assert response.status_code == 200
