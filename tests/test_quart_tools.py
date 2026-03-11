from quart import Quart
import pytest

from other.quart_tools import get_ip


async def _make_request(headers=None):
    app = Quart(__name__)

    @app.get("/")
    async def index():
        return {"ip": await get_ip()}

    test_client = app.test_client()
    response = await test_client.get("/", headers=headers or {})
    return await response.get_json()


@pytest.mark.asyncio
async def test_get_ip_prefers_x_forwarded_for():
    data = await _make_request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert data["ip"] == "1.2.3.4"


@pytest.mark.asyncio
async def test_get_ip_falls_back_to_x_real_ip():
    data = await _make_request({"X-Real-IP": "9.8.7.6"})
    assert data["ip"] == "9.8.7.6"


@pytest.mark.asyncio
async def test_get_ip_uses_remote_addr_when_no_headers():
    data = await _make_request()
    assert data["ip"] == "<local>"
