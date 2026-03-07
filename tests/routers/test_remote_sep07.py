import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_remote_sep07_success(client):
    """Test successful submission of XDR"""
    valid_xdr = "AAAAAA=="  # Valid Base64
    mock_service_result = {
        "SUCCESS": True,
        "hash": "test_hash_123",
        "MESSAGES": ["Added signature"],
    }

    # Patch TransactionService in the module where it is used (routers.remote_sep07)
    # We patch the class so that when it's instantiated, it returns our mock
    with patch("routers.remote_sep07.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.sign_transaction_from_xdr = AsyncMock(
            return_value=mock_service_result
        )

        response = await client.post("/remote/sep07", form={"xdr": valid_xdr})

        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "pending"
        assert data["hash"] == "test_hash_123"


@pytest.mark.asyncio
async def test_remote_sep07_invalid_base64(client):
    """Test submission of invalid Base64"""
    invalid_xdr = "NotBase64!"

    response = await client.post("/remote/sep07", form={"xdr": invalid_xdr})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["status"] == "failed"
    assert "Invalid or missing base64" in data["error"]["message"]


@pytest.mark.asyncio
async def test_remote_sep07_missing_xdr(client):
    """Test submission with missing XDR"""
    response = await client.post("/remote/sep07", form={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["status"] == "failed"


@pytest.mark.asyncio
async def test_remote_sep07_service_failure(client):
    """Test when service returns failure (e.g. transaction not found)"""
    valid_xdr = "AAAAAA=="
    mock_service_result = {
        "SUCCESS": False,
        "hash": "",
        "MESSAGES": ["Transaction not found"],
    }

    with patch("routers.remote_sep07.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.sign_transaction_from_xdr = AsyncMock(
            return_value=mock_service_result
        )

        response = await client.post("/remote/sep07", form={"xdr": valid_xdr})

        assert response.status_code == 404
        data = await response.get_json()
        assert data["status"] == "failed"
        assert "Transaction not found" in data["error"]["message"]


@pytest.mark.asyncio
async def test_remote_sep07_add_missing_uri(client):
    response = await client.post("/remote/sep07/add", json={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "Missing URI"


@pytest.mark.asyncio
async def test_remote_sep07_get_returns_404_for_unknown_uri(client):
    response = await client.get("/remote/sep07/get/missing")

    assert response.status_code == 404
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "URI not found"


@pytest.mark.asyncio
async def test_remote_sep07_parse_uri_requires_uri(client):
    response = await client.post("/remote/sep07/parse-uri", json={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "URI is required"


@pytest.mark.asyncio
async def test_remote_sep07_parse_uri_requires_xdr_param(client):
    response = await client.post(
        "/remote/sep07/parse-uri",
        json={"uri": "web+stellar:tx?callback=url:https://example.com/callback"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "No XDR found in URI"


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_requires_payload(client):
    response = await client.post("/remote/sep07/submit-signed", json={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "signed_xdr and callback_url are required"


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_validates_base64(client):
    response = await client.post(
        "/remote/sep07/submit-signed",
        json={"signed_xdr": "not-base64", "callback_url": "https://example.com"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "Invalid signed XDR format"
