import pytest
from unittest.mock import patch
from datetime import datetime

from db.sql_models import Addresses

@pytest.mark.asyncio
async def test_federal_federation_name(client, app, db_session):
    """Test /federation?q=name&type=name"""
    address = Addresses(
        stellar_address="test*eurmtl.me",
        account_id="GABC",
        memo=None,
        add_dt=datetime(2024, 1, 1, 0, 0, 0),
        updated_dt=datetime(2024, 1, 1, 0, 0, 0),
    )
    db_session.add(address)
    await db_session.commit()
    
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
