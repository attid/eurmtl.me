import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_federal_federation_name(client, app):
    """Test /federation?q=name&type=name"""
    mock_address = MagicMock()
    mock_address.stellar_address = "test*eurmtl.me"
    mock_address.account_id = "GABC"
    mock_address.memo = None
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_address
    
    # Mocking the session.execute call
    app.db_pool.return_value.__aenter__.return_value.execute = AsyncMock(return_value=mock_result)
    
    response = await client.get("/federation?q=test*eurmtl.me&type=name")
    assert response.status_code == 200
    data = await response.get_json()
    assert data["stellar_address"] == "test*eurmtl.me"
    assert data["account_id"] == "GABC"

@pytest.mark.asyncio
async def test_federal_stellar_toml(client):
    """Test /.well-known/stellar.toml"""
    response = await client.get("/.well-known/stellar.toml")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/plain"

@pytest.mark.asyncio
async def test_federal_sep6_info(client):
    """Test /sep6/info"""
    response = await client.get("/sep6/info")
    assert response.status_code == 200
    data = await response.get_json()
    assert "deposit" in data

@pytest.mark.asyncio
async def test_federal_sep10_auth(client):
    """Test /auth (SEP-10)"""
    with patch("routers.federal.build_challenge_transaction", return_value="challenge_xdr"):
        response = await client.get("/auth?account=GABC&home_domain=eurmtl.me")
        assert response.status_code == 200
        data = await response.get_json()
        assert data["transaction"] == "challenge_xdr"
