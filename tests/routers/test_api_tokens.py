"""API-токены: жизненный цикл (создание, один активный, отзыв) и /token."""

import hashlib

import pytest
from sqlalchemy import select

from db.sql_models import ApiToken
from routers.token import create_token, hash_token, scope_allows

TEST_USERDATA = {"id": 1837984392, "username": "itolstov"}


async def _active_tokens(db_pool, tg_id):
    async with db_pool() as session:
        result = await session.execute(
            select(ApiToken).filter(
                ApiToken.tg_id == tg_id, ApiToken.revoked_at.is_(None)
            )
        )
        return result.scalars().all()


async def _all_tokens(db_pool, tg_id):
    async with db_pool() as session:
        result = await session.execute(select(ApiToken).filter(ApiToken.tg_id == tg_id))
        return result.scalars().all()


@pytest.mark.asyncio
async def test_create_token_stores_hash_not_raw(db_pool):
    async with db_pool() as session:
        raw = await create_token(session, TEST_USERDATA["id"], "itolstov", "d2")
    assert len(raw) == 32 and all(c in "0123456789abcdef" for c in raw)  # 32 hex
    tokens = await _all_tokens(db_pool, TEST_USERDATA["id"])
    assert len(tokens) == 1
    assert tokens[0].token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert tokens[0].revoked_at is None
    assert tokens[0].username == "itolstov"


@pytest.mark.asyncio
async def test_new_token_revokes_previous(db_pool):
    async with db_pool() as session:
        await create_token(session, TEST_USERDATA["id"], "itolstov", "d2")
        raw2 = await create_token(session, TEST_USERDATA["id"], "itolstov", "d2")
    active = await _active_tokens(db_pool, TEST_USERDATA["id"])
    assert len(active) == 1
    assert active[0].token_hash == hash_token(raw2)
    tokens = await _all_tokens(db_pool, TEST_USERDATA["id"])
    assert len(tokens) == 2
    assert tokens[0].revoked_at is not None  # старый умер


@pytest.mark.asyncio
async def test_scope_allows_granules():
    assert scope_allows("d2", "d2")
    assert not scope_allows("d2", "d2_publish")
    assert scope_allows("d2,d2_publish", "d2_publish")
    assert not scope_allows("", "d2")


@pytest.mark.asyncio
async def test_token_page_requires_login(client):
    response = await client.get("/token")
    assert response.status_code == 302


@pytest.mark.asyncio
async def test_token_page_create_shows_once(client, db_pool):
    async with client.session_transaction() as session:
        session["userdata"] = TEST_USERDATA
        session["user_id"] = TEST_USERDATA["id"]

    response = await client.post("/token", form={"action": "create"})
    assert response.status_code == 200
    html = await response.get_data(as_text=True)
    tokens = await _active_tokens(db_pool, TEST_USERDATA["id"])
    assert len(tokens) == 1
    raw_hash = tokens[0].token_hash
    # Токен из ответа совпадает с тем, что в БД (хешем).
    import re

    match = re.search(
        r'<pre class="m-2 p-2 bg-secondary-lt rounded user-select-all">([0-9a-f]{32})</pre>',
        html,
    )
    assert match, "токен должен быть показан на странице"
    assert hashlib.sha256(match.group(1).encode()).hexdigest() == raw_hash

    # GET после создания токен больше не показывает.
    response = await client.get("/token")
    html = await response.get_data(as_text=True)
    assert re.search(r"[0-9a-f]{32}", html) is None or "активен" in html


@pytest.mark.asyncio
async def test_token_page_create_without_username_rejected(client, db_pool):
    """userdata без username (Telegram-аккаунт без @handle) — 500 недопустим."""
    async with client.session_transaction() as session:
        session["userdata"] = {"id": TEST_USERDATA["id"], "username": None}
        session["user_id"] = TEST_USERDATA["id"]

    response = await client.post("/token", form={"action": "create"})
    assert response.status_code == 302  # flash + redirect, не 500
    assert await _active_tokens(db_pool, TEST_USERDATA["id"]) == []


@pytest.mark.asyncio
async def test_token_page_revoke_without_username_ok(client, db_pool):
    """Ревок у юзера без username — не 500 (KeyError в логгере, круг 2)."""
    async with client.session_transaction() as session:
        session["userdata"] = {"id": TEST_USERDATA["id"], "username": None}
        session["user_id"] = TEST_USERDATA["id"]
    async with db_pool() as session:
        await create_token(session, TEST_USERDATA["id"], "itolstov", "d2")

    response = await client.post("/token", form={"action": "revoke"})
    assert response.status_code == 302
    assert await _active_tokens(db_pool, TEST_USERDATA["id"]) == []


@pytest.mark.asyncio
async def test_token_page_revoke(client, db_pool):
    async with client.session_transaction() as session:
        session["userdata"] = TEST_USERDATA
        session["user_id"] = TEST_USERDATA["id"]
    async with db_pool() as session:
        await create_token(session, TEST_USERDATA["id"], "itolstov", "d2")

    response = await client.post("/token", form={"action": "revoke"})
    assert response.status_code == 302
    assert await _active_tokens(db_pool, TEST_USERDATA["id"]) == []
