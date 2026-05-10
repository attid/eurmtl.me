from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text


async def _get_latest_token(db_session) -> dict:
    result = await db_session.execute(
        text(
            "select token, status, userdata_json, return_to, created_at, expires_at, "
            "confirmed_at, used_at from t_bot_login_tokens order by created_at desc"
        )
    )
    row = result.mappings().first()
    assert row is not None
    return dict(row)


async def _set_token_state(
    db_session,
    token: str,
    *,
    status: str,
    userdata_json: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    await db_session.execute(
        text(
            "update t_bot_login_tokens "
            "set status = :status, userdata_json = :userdata_json, "
            "expires_at = :expires_at, confirmed_at = :confirmed_at "
            "where token = :token"
        ),
        {
            "token": token,
            "status": status,
            "userdata_json": userdata_json,
            "expires_at": expires_at
            or datetime.now(timezone.utc) + timedelta(minutes=5),
            "confirmed_at": datetime.now(timezone.utc)
            if status == "confirmed"
            else None,
        },
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_login_page_links_to_bot_fallback_flow(client):
    response = await client.get("/login")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'href="/login/bot"' in body
    assert "telegram-widget.js" not in body


@pytest.mark.asyncio
async def test_login_bot_creates_pending_session_bound_token(client, db_session):
    response = await client.get("/login/bot")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    token_row = await _get_latest_token(db_session)
    token = token_row["token"]
    assert token_row["status"] == "pending"
    assert token_row["return_to"] is None
    assert f"start=eurmtl_{token}" in body
    assert f"/login/bot/status/{token}" in body

    async with client.session_transaction() as test_session:
        assert test_session["bot_login_token"] == token


@pytest.mark.asyncio
async def test_login_bot_preserves_return_to(client, db_session):
    async with client.session_transaction() as test_session:
        test_session["return_to"] = "https://eurmtl.me/sign_tools/abc"

    response = await client.get("/login/bot")

    assert response.status_code == 200
    token_row = await _get_latest_token(db_session)
    assert token_row["return_to"] == "https://eurmtl.me/sign_tools/abc"


@pytest.mark.asyncio
async def test_bot_confirm_requires_eurmtl_key(client):
    response = await client.post(
        "/login/bot/confirm",
        json={"token": "abc", "id": 123, "username": "alice"},
    )

    assert response.status_code == 401
    assert await response.get_json() == {"status": "error", "message": "unauthorized"}


@pytest.mark.asyncio
async def test_bot_confirm_marks_pending_token_confirmed(client, db_session):
    await client.get("/login/bot")
    token = (await _get_latest_token(db_session))["token"]

    with patch("routers.index.config.eurmtl_key.get_secret_value") as secret:
        secret.return_value = "test-eurmtl-key"
        response = await client.post(
            "/login/bot/confirm",
            headers={"Authorization": "Bearer test-eurmtl-key"},
            json={
                "token": token,
                "id": 123456,
                "first_name": "Alice",
                "last_name": "",
                "username": "alice",
                "photo_url": None,
                "auth_date": 1760000000,
            },
        )

    assert response.status_code == 200
    assert await response.get_json() == {"status": "ok"}
    token_row = await _get_latest_token(db_session)
    assert token_row["status"] == "confirmed"
    assert '"username": "alice"' in token_row["userdata_json"]
    assert token_row["confirmed_at"] is not None


@pytest.mark.asyncio
async def test_bot_confirm_rejects_expired_token(client, db_session):
    await client.get("/login/bot")
    token = (await _get_latest_token(db_session))["token"]
    await _set_token_state(
        db_session,
        token,
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    with patch("routers.index.config.eurmtl_key.get_secret_value") as secret:
        secret.return_value = "test-eurmtl-key"
        response = await client.post(
            "/login/bot/confirm",
            headers={"Authorization": "Bearer test-eurmtl-key"},
            json={"token": token, "id": 123456, "username": "alice"},
        )

    assert response.status_code == 400
    assert await response.get_json() == {"status": "error", "message": "expired"}
    token_row = await _get_latest_token(db_session)
    assert token_row["status"] == "expired"


@pytest.mark.asyncio
async def test_bot_status_pending_does_not_create_session(client, db_session):
    await client.get("/login/bot")
    token = (await _get_latest_token(db_session))["token"]

    response = await client.get(f"/login/bot/status/{token}")

    assert response.status_code == 200
    assert await response.get_json() == {"status": "pending"}
    async with client.session_transaction() as test_session:
        assert "userdata" not in test_session
        assert "user_id" not in test_session


@pytest.mark.asyncio
async def test_bot_status_rejects_non_session_token(client, db_session):
    await client.get("/login/bot")
    token = (await _get_latest_token(db_session))["token"]

    async with client.session_transaction() as test_session:
        test_session["bot_login_token"] = "other-token"

    response = await client.get(f"/login/bot/status/{token}")

    assert response.status_code == 403
    assert await response.get_json() == {"status": "error", "message": "forbidden"}


@pytest.mark.asyncio
async def test_bot_status_expired_stops_flow(client, db_session):
    await client.get("/login/bot")
    token = (await _get_latest_token(db_session))["token"]
    await _set_token_state(
        db_session,
        token,
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    response = await client.get(f"/login/bot/status/{token}")

    assert response.status_code == 200
    assert await response.get_json() == {"status": "expired"}
    token_row = await _get_latest_token(db_session)
    assert token_row["status"] == "expired"


@pytest.mark.asyncio
async def test_bot_status_confirmed_creates_session_and_uses_token(client, db_session):
    await client.get("/login/bot")
    token = (await _get_latest_token(db_session))["token"]
    await _set_token_state(
        db_session,
        token,
        status="confirmed",
        userdata_json=(
            '{"id": 123456, "first_name": "Alice", "last_name": "", '
            '"username": "alice", "photo_url": null, "auth_date": 1760000000, '
            '"hash": null}'
        ),
    )

    response = await client.get(f"/login/bot/status/{token}")

    assert response.status_code == 200
    assert await response.get_json() == {"status": "confirmed", "redirect": "/lab"}
    async with client.session_transaction() as test_session:
        assert test_session["user_id"] == 123456
        assert test_session["userdata"]["username"] == "alice"
        assert "bot_login_token" not in test_session
    token_row = await _get_latest_token(db_session)
    assert token_row["status"] == "used"
    assert token_row["used_at"] is not None


@pytest.mark.asyncio
async def test_bot_status_confirmed_respects_return_to(client, db_session):
    async with client.session_transaction() as test_session:
        test_session["return_to"] = "https://eurmtl.me/sign_tools/abc"

    await client.get("/login/bot")
    token = (await _get_latest_token(db_session))["token"]
    await _set_token_state(
        db_session,
        token,
        status="confirmed",
        userdata_json='{"id": 123456, "username": "alice", "hash": null}',
    )

    response = await client.get(f"/login/bot/status/{token}")

    assert response.status_code == 200
    assert await response.get_json() == {
        "status": "confirmed",
        "redirect": "https://eurmtl.me/sign_tools/abc",
    }
