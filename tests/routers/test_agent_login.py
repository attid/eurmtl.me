"""Tests for agent signer login (/login/agent)."""

import base64
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from stellar_sdk import Keypair

from routers import agent_login


def _fund_signers(address: str, weight: int = 5) -> dict:
    return {"signers": [{"key": address, "weight": weight}]}


def _grist_user(address: str) -> SimpleNamespace:
    return SimpleNamespace(account_id=address, telegram_id=424242, username="@AgentBot")


async def _get_nonce(client) -> str:
    response = await client.get("/login/agent")
    assert response.status_code == 200
    return (await response.get_json())["nonce"]


@pytest.mark.asyncio
async def test_agent_login_openapi_and_llms_reference(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/login/agent" in (await response.get_json())["paths"]

    response = await client.get("/llms.txt")
    body = await response.get_data(as_text=True)
    assert "GET /login/agent" in body
    assert "POST /login/agent" in body


@pytest.mark.asyncio
async def test_agent_login_happy_path_sets_session(client):
    kp = Keypair.random()
    nonce = await _get_nonce(client)

    with (
        patch_fund_signers(kp.public_key),
        patch(
            "routers.agent_login.load_user_from_grist",
            new=AsyncMock(return_value=_grist_user(kp.public_key)),
        ),
    ):
        response = await client.post(
            "/login/agent",
            json={
                "address": kp.public_key,
                "nonce": nonce,
                "signature": base64.b64encode(kp.sign(nonce.encode())).decode(),
            },
        )

    assert response.status_code == 200
    assert await response.get_json() == {"status": "ok"}

    async with client.session_transaction() as test_session:
        assert test_session["user_id"] == "424242"
        assert test_session["userdata"]["username"] == "AgentBot"
        assert test_session["userdata"]["id"] == "424242"


@pytest.mark.asyncio
async def test_agent_login_nonce_single_use(client):
    kp = Keypair.random()
    nonce = await _get_nonce(client)
    body = {
        "address": kp.public_key,
        "nonce": nonce,
        "signature": base64.b64encode(kp.sign(nonce.encode())).decode(),
    }

    with (
        patch_fund_signers(kp.public_key),
        patch(
            "routers.agent_login.load_user_from_grist",
            new=AsyncMock(return_value=_grist_user(kp.public_key)),
        ),
    ):
        first = await client.post("/login/agent", json=body)
        second = await client.post("/login/agent", json=body)

    assert first.status_code == 200
    assert second.status_code == 400
    assert (await second.get_json())["message"] == "nonce_expired"


@pytest.mark.asyncio
async def test_agent_login_nonce_expired(client):
    kp = Keypair.random()
    nonce = await _get_nonce(client)
    agent_login._agent_nonce_store[nonce] = time.monotonic() - 120

    response = await client.post(
        "/login/agent",
        json={
            "address": kp.public_key,
            "nonce": nonce,
            "signature": base64.b64encode(kp.sign(nonce.encode())).decode(),
        },
    )

    assert response.status_code == 400
    assert (await response.get_json())["message"] == "nonce_expired"


@pytest.mark.asyncio
async def test_agent_login_bad_signature(client):
    kp = Keypair.random()
    nonce = await _get_nonce(client)

    response = await client.post(
        "/login/agent",
        json={
            "address": kp.public_key,
            "nonce": nonce,
            "signature": base64.b64encode(kp.sign(b"other payload")).decode(),
        },
    )

    assert response.status_code == 400
    assert (await response.get_json())["message"] == "bad_signature"


@pytest.mark.asyncio
async def test_agent_login_garbage_signature(client):
    kp = Keypair.random()
    nonce = await _get_nonce(client)

    response = await client.post(
        "/login/agent",
        json={"address": kp.public_key, "nonce": nonce, "signature": "not-base64!!"},
    )

    assert response.status_code == 400
    assert (await response.get_json())["message"] == "bad_signature"


@pytest.mark.asyncio
async def test_agent_login_bad_address(client):
    nonce = await _get_nonce(client)

    response = await client.post(
        "/login/agent",
        json={"address": "G_INVALID", "nonce": nonce, "signature": "AA=="},
    )

    assert response.status_code == 400
    assert (await response.get_json())["message"] == "bad_address"


@pytest.mark.asyncio
async def test_agent_login_not_a_signer(client):
    outsider = Keypair.random()
    nonce = await _get_nonce(client)

    with patch_fund_signers(Keypair.random().public_key):
        response = await client.post(
            "/login/agent",
            json={
                "address": outsider.public_key,
                "nonce": nonce,
                "signature": base64.b64encode(outsider.sign(nonce.encode())).decode(),
            },
        )

    assert response.status_code == 403
    assert (await response.get_json())["message"] == "not_a_signer"


@pytest.mark.asyncio
async def test_agent_login_no_grist_user(client):
    kp = Keypair.random()
    nonce = await _get_nonce(client)

    with (
        patch_fund_signers(kp.public_key),
        patch(
            "routers.agent_login.load_user_from_grist", new=AsyncMock(return_value=None)
        ),
    ):
        response = await client.post(
            "/login/agent",
            json={
                "address": kp.public_key,
                "nonce": nonce,
                "signature": base64.b64encode(kp.sign(nonce.encode())).decode(),
            },
        )

    assert response.status_code == 403
    assert (await response.get_json())["message"] == "no_grist_user"


def patch_fund_signers(address: str):
    return patch(
        "routers.agent_login.get_fund_signers",
        new=AsyncMock(return_value=_fund_signers(address)),
    )
