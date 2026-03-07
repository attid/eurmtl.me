import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_index_root(client):
    """Test root route /"""
    response = await client.get("/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_index_mytest(client):
    """Test /mytest route"""
    response = await client.get("/mytest")
    assert response.status_code == 200
    assert (await response.get_data(as_text=True)) == "***"


@pytest.mark.asyncio
async def test_index_uuid(client):
    """Test /uuid route"""
    response = await client.get("/uuid")
    assert response.status_code == 200
    data = await response.get_data(as_text=True)
    assert len(data) == 32  # hex uuid is 32 chars


@pytest.mark.asyncio
async def test_index_err_no_auth(client):
    """Test /err without auth"""
    with patch("routers.index.check_user_weight", new=AsyncMock(return_value=0)):
        response = await client.get("/err")
        assert (await response.get_data(as_text=True)) == "need authority"


@pytest.mark.asyncio
async def test_index_err_with_auth_no_file(client):
    """Test /err with auth but no log file"""
    with patch("routers.index.check_user_weight", new=AsyncMock(return_value=1)):
        with patch("os.path.isfile", return_value=False):
            response = await client.get("/err")
            assert (await response.get_data(as_text=True)) == "No error"


@pytest.mark.asyncio
async def test_index_myip(client):
    """Test /myip route"""
    # Mock get_ip since it might depend on external services or request headers
    with patch("routers.index.get_ip", new=AsyncMock(return_value="127.0.0.1")):
        response = await client.get("/myip")
        assert (await response.get_data(as_text=True)) == "127.0.0.1"


@pytest.mark.asyncio
async def test_llm_txt_exposes_machine_api_overview(client):
    """Test /llm.txt machine-readable entrypoint."""
    response = await client.get("/llm.txt")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"

    body = await response.get_data(as_text=True)
    assert "EURMTL machine API guide" in body
    assert "GET /llm.txt" in body
    assert "POST /remote/decode" in body
    assert "POST /remote/sep07/auth/init" in body
    assert "GET /.well-known/stellar.toml" in body
