from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from jwt import InvalidSignatureError

from db.sql_models import Signers


@pytest.mark.asyncio
async def test_login_page_uses_oidc_button_instead_of_legacy_widget(client):
    response = await client.get("/login")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "telegram-widget.js" not in body
    assert 'href="/login/telegram"' in body
    assert "Войти через Telegram" in body
    assert "номер телефона" not in body


@pytest.mark.asyncio
async def test_login_telegram_stores_session_values_and_redirects_to_auth(client):
    response = await client.get("/login/telegram")

    assert response.status_code == 302
    location = response.headers["Location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://oauth.telegram.org/auth"
    )
    assert query["scope"] == ["openid profile"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["https://eurmtl.me/login/telegram/callback"]

    async with client.session_transaction() as test_session:
        assert test_session["telegram_oidc_state"] == query["state"][0]
        assert test_session["telegram_oidc_nonce"] == query["nonce"][0]
        assert test_session["telegram_oidc_code_verifier"]


@pytest.mark.asyncio
async def test_telegram_callback_with_invalid_state_does_not_login(client):
    async with client.session_transaction() as test_session:
        test_session["telegram_oidc_state"] = "expected-state"
        test_session["telegram_oidc_nonce"] = "nonce"
        test_session["telegram_oidc_code_verifier"] = "verifier"

    response = await client.get("/login/telegram/callback?state=wrong&code=abc")

    assert response.status_code == 400
    assert "Invalid Telegram login state" in await response.get_data(as_text=True)
    async with client.session_transaction() as test_session:
        assert "userdata" not in test_session
        assert "user_id" not in test_session


@pytest.mark.asyncio
async def test_telegram_callback_without_code_does_not_login(client):
    async with client.session_transaction() as test_session:
        test_session["telegram_oidc_state"] = "state"
        test_session["telegram_oidc_nonce"] = "nonce"
        test_session["telegram_oidc_code_verifier"] = "verifier"

    response = await client.get("/login/telegram/callback?state=state")

    assert response.status_code == 400
    assert "Missing Telegram login code" in await response.get_data(as_text=True)
    async with client.session_transaction() as test_session:
        assert "userdata" not in test_session
        assert "user_id" not in test_session


@pytest.mark.asyncio
async def test_telegram_callback_token_error_does_not_login(client):
    async with client.session_transaction() as test_session:
        test_session["telegram_oidc_state"] = "state"
        test_session["telegram_oidc_nonce"] = "nonce"
        test_session["telegram_oidc_code_verifier"] = "verifier"

    with patch(
        "routers.index.exchange_telegram_code",
        new=AsyncMock(side_effect=ValueError("token endpoint failed")),
    ):
        response = await client.get("/login/telegram/callback?state=state&code=abc")

    assert response.status_code == 400
    assert "Telegram authorization failed" in await response.get_data(as_text=True)
    async with client.session_transaction() as test_session:
        assert "userdata" not in test_session
        assert "user_id" not in test_session


@pytest.mark.asyncio
async def test_telegram_callback_invalid_jwt_does_not_login(client):
    async with client.session_transaction() as test_session:
        test_session["telegram_oidc_state"] = "state"
        test_session["telegram_oidc_nonce"] = "nonce"
        test_session["telegram_oidc_code_verifier"] = "verifier"

    with (
        patch(
            "routers.index.exchange_telegram_code",
            new=AsyncMock(return_value={"id_token": "id-token"}),
        ),
        patch(
            "routers.index.decode_telegram_id_token",
            side_effect=InvalidSignatureError("bad signature"),
        ),
    ):
        response = await client.get("/login/telegram/callback?state=state&code=abc")

    assert response.status_code == 400
    assert "Telegram authorization failed" in await response.get_data(as_text=True)
    async with client.session_transaction() as test_session:
        assert "userdata" not in test_session
        assert "user_id" not in test_session


@pytest.mark.asyncio
async def test_telegram_callback_success_creates_session_and_updates_signer(
    client, db_session
):
    signer = Signers(
        id=101,
        tg_id=None,
        username="alice",
        public_key="GA" + "A" * 54,
        signature_hint="abcd1234",
    )
    db_session.add(signer)
    await db_session.commit()

    async with client.session_transaction() as test_session:
        test_session["telegram_oidc_state"] = "state"
        test_session["telegram_oidc_nonce"] = "nonce"
        test_session["telegram_oidc_code_verifier"] = "verifier"

    claims = {
        "iss": "https://oauth.telegram.org",
        "aud": "client-id",
        "nonce": "nonce",
        "exp": 4102444800,
        "sub": "sub-123",
        "id": 777,
        "name": "Alice",
        "preferred_username": "alice",
        "picture": "https://cdn.example/alice.jpg",
        "iat": 1710000000,
    }

    with (
        patch(
            "routers.index.exchange_telegram_code",
            new=AsyncMock(return_value={"id_token": "id-token"}),
        ) as exchange,
        patch("routers.index.decode_telegram_id_token", return_value=claims),
    ):
        response = await client.get("/login/telegram/callback?state=state&code=abc")

    assert response.status_code == 302
    assert response.headers["Location"] == "/lab"
    exchange.assert_awaited_once()

    async with client.session_transaction() as test_session:
        assert test_session["user_id"] == 777
        assert test_session["userdata"] == {
            "id": 777,
            "first_name": "Alice",
            "last_name": "",
            "username": "alice",
            "photo_url": "https://cdn.example/alice.jpg",
            "auth_date": 1710000000,
            "hash": None,
        }
        assert "telegram_oidc_state" not in test_session
        assert "telegram_oidc_nonce" not in test_session
        assert "telegram_oidc_code_verifier" not in test_session

    await db_session.refresh(signer)
    assert signer.tg_id == 777


@pytest.mark.asyncio
async def test_telegram_callback_success_respects_return_to(client):
    async with client.session_transaction() as test_session:
        test_session["telegram_oidc_state"] = "state"
        test_session["telegram_oidc_nonce"] = "nonce"
        test_session["telegram_oidc_code_verifier"] = "verifier"
        test_session["return_to"] = "https://eurmtl.me/sign_tools/abc"

    claims = {
        "iss": "https://oauth.telegram.org",
        "aud": "client-id",
        "nonce": "nonce",
        "exp": 4102444800,
        "sub": "sub-123",
        "preferred_username": "alice",
    }

    with (
        patch(
            "routers.index.exchange_telegram_code",
            new=AsyncMock(return_value={"id_token": "id-token"}),
        ),
        patch("routers.index.decode_telegram_id_token", return_value=claims),
    ):
        response = await client.get("/login/telegram/callback?state=state&code=abc")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://eurmtl.me/sign_tools/abc"
    async with client.session_transaction() as test_session:
        assert test_session["user_id"] == "sub-123"
