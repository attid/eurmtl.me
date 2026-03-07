import pytest
from unittest.mock import AsyncMock, patch

INVALID_STELLAR_XDR = "AAAAAgAAAAA+gj+9R9RakwtxBG6Up8jAewUfdurumKJARnpcMG9VBgAAAZADqmC9AAAACQAAAAEAAAAAAAAAAAAAAABprWevAAAAAQAAAARleGNoAAAAAgAAAAAAAAABAAAAAOULguv++61OnAUgnSV24FKlgUt80KvaUijNM9Fdx2wmAAAAAkVVUk1UTAAAAAAAAAAAAAAEqbejBk1rxsHVls854RnAyfpJaZacvgwmQ0jxNDBvqgAAAAFloLwAAAAAAAAAAAMAAAACRVVSTVRMAAAAAAAAAAAAAASpt6MGTWvGwdWWzznhGcDJ+klplpy+DCZDSPE0MG+qAAAAAVVTRE0AAAAAzjFwwWvYRuQOCHjRQ12ZsvHFXsmtQ0ka1OpQTcuL5UoAAAAAAAAAAAAAAAEAAAABAAAAAGzhWBAAAAAAAAAAAjBvVQYAAABA8ngRn6FosWJoKr+CiNwUecKAkHp4oOTfCc3hSeFBWUNfbddyxouSs9LrkX6Yym7KUpqlbr35eypU0gUOs9bEBVpCAfwAAABAKQso0UED2q9QpUa1jIHCGtWkFCgHu7OAzYodR4L3K+HOY0OGtqIRomGNwJ2/hSP6CUc7uAJryU33J1osSvUwDQ=="


@pytest.mark.asyncio
async def test_remote_need_sign(client):
    """Test /remote/need_sign/<public_key>"""
    with patch("routers.remote.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.get_pending_transactions_for_signer = AsyncMock(return_value=[])

        response = await client.get("/remote/need_sign/GABC")
        assert response.status_code == 200
        assert await response.get_json() == []


@pytest.mark.asyncio
async def test_remote_update_signature(client):
    """Test /remote/update_signature"""
    with patch("routers.remote.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.sign_transaction_from_xdr = AsyncMock(
            return_value={"SUCCESS": True}
        )

        response = await client.post(
            "/remote/update_signature", json={"xdr": "AAAAAA=="}
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_remote_decode_xdr(client):
    """Test /remote/decode"""
    with patch(
        "routers.remote.decode_xdr_to_text", new=AsyncMock(return_value=["Line 1"])
    ):
        response = await client.post("/remote/decode", json={"xdr": "AAAAAA=="})
        assert response.status_code == 200
        data = await response.get_json()
        assert "Line 1" in data["text"]


@pytest.mark.asyncio
async def test_remote_decode_xdr_returns_400_for_invalid_stellar_xdr(client):
    """Валидный base64, но невалидный Stellar XDR должен вернуть 400."""
    with patch(
        "routers.remote.decode_xdr_to_text",
        new=AsyncMock(side_effect=ValueError("Invalid Stellar XDR")),
    ):
        response = await client.post(
            "/remote/decode", json={"xdr": INVALID_STELLAR_XDR}
        )

    assert response.status_code == 400
    assert await response.get_json() == {"error": "Invalid Stellar XDR"}


@pytest.mark.asyncio
async def test_remote_get_xdr(client):
    """Test /remote/get_xdr/<hash>"""
    mock_tx = AsyncMock()
    mock_tx.body = "AAAA..."

    with patch("routers.remote.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.get_transaction_by_hash = AsyncMock(return_value=mock_tx)

        response = await client.get(
            "/remote/get_xdr/0000000000000000000000000000000000000000000000000000000000000000"
        )
        assert response.status_code == 200
        data = await response.get_json()
        assert data["xdr"] == "AAAA..."
