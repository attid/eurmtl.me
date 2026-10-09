"""Тесты JSON-ветки POST /sign_tools (fetch из d2_tx_modal.html)."""

from unittest.mock import AsyncMock, patch

import pytest

XDR = "AAAAAGL8HQvQkbK2HA3W8VtrnWejk5MGiHRT52w77DhEUv%2FfAAAAZAAAB4sAAABaAAAAAQAAAAAAAAAAAAAAAQAAAAAAAAABAAAAAE9wdGlvbgAAAAAAAAABAAAAAAAAAAI="


@pytest.fixture
def _add_tx_ok():
    """add_transaction возвращает успех и фиксированный hash."""
    with patch(
        "routers.sign_tools.add_transaction",
        new=AsyncMock(return_value=(True, "a" * 64)),
    ) as mock:
        yield mock


async def _post_json(client, payload):
    return await client.post(
        "/sign_tools",
        form=payload,
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


@pytest.mark.asyncio
async def test_post_json_returns_url(client, _add_tx_ok):
    response = await _post_json(
        client, {"xdr": XDR, "description": "Вопрос 4: тест", "memo": "мемо"}
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["url"] == "/sign_tools/" + "a" * 64


@pytest.mark.asyncio
async def test_post_json_duplicate_same_url(client, _add_tx_ok):
    await _post_json(client, {"xdr": XDR, "description": "Вопрос 4: тест", "memo": ""})
    second = await _post_json(
        client, {"xdr": XDR, "description": "Вопрос 4: тест", "memo": ""}
    )
    assert second.status_code == 200
    assert (await second.get_json())["url"] == "/sign_tools/" + "a" * 64


@pytest.mark.asyncio
async def test_post_json_error_400(client, _add_tx_ok):
    response = await _post_json(client, {"xdr": XDR, "description": "ок", "memo": ""})
    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_post_without_header_redirects(client, _add_tx_ok):
    response = await client.post(
        "/sign_tools",
        form={"xdr": XDR, "description": "Вопрос 4: тест", "memo": ""},
    )
    assert response.status_code == 302
