import hashlib
import secrets
from datetime import datetime, timezone

from loguru import logger
from quart import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
)
from sqlalchemy import select, update

from db.sql_models import ApiToken

blueprint = Blueprint("api_token", __name__)


def generate_token() -> str:
    """128 бит энтропии, 32 hex-символа."""
    return secrets.token_hex(16)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def revoke_active_tokens(db_session, tg_id: int) -> None:
    """«Один активный на юзера»: отзыв всех живых токенов одним UPDATE."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db_session.execute(
        update(ApiToken)
        .where(ApiToken.tg_id == tg_id, ApiToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def create_token(db_session, tg_id: int, username: str, scope: str) -> str:
    """Создать токен, отозвав предыдущие. Возвращает сырой токен (один раз).
    Коммитит сессию (revocation + insert атомарно)."""
    await revoke_active_tokens(db_session, tg_id)
    raw = generate_token()
    db_session.add(
        ApiToken(
            token_hash=hash_token(raw),
            tg_id=tg_id,
            username=username.removeprefix("@"),
            scope=scope,
        )
    )
    await db_session.commit()
    return raw


async def authenticate_bearer(authorization_header: str | None):
    """Bearer-токен → ApiToken | None. Только активные, не отозванные."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return None
    raw = authorization_header.removeprefix("Bearer ").strip()
    if not raw:
        return None
    async with current_app.db_pool() as db_session:
        result = await db_session.execute(
            select(ApiToken).filter(
                ApiToken.token_hash == hash_token(raw),
                ApiToken.revoked_at.is_(None),
            )
        )
        return result.scalars().first()


def scope_allows(scope: str, granule: str) -> bool:
    """Гранулы через запятую: 'd2' или 'd2,d2_publish'."""
    return granule in [g.strip() for g in (scope or "").split(",") if g.strip()]


async def _active_token_row(db_session, tg_id: int):
    """Активный токен пользователя для карточки на /token."""
    result = await db_session.execute(
        select(ApiToken)
        .filter(ApiToken.tg_id == tg_id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
    )
    return result.scalars().first()


@blueprint.route("/token", methods=("GET", "POST"))
async def token_page():
    userdata = session.get("userdata")
    if userdata is None:
        return redirect("/login")

    try:
        tg_id = int(userdata.get("id"))
    except (TypeError, ValueError):
        return redirect("/login")
    async with current_app.db_pool() as db_session:
        if request.method == "POST":
            form = await request.form
            action = form.get("action", "")
            if action == "create":
                username = userdata.get("username")
                if not username:
                    await flash(
                        "Для выпуска API-токена нужен Telegram @username — "
                        "задайте его в настройках Telegram и перезайдите.",
                        "error",
                    )
                    return redirect("/token")
                raw = await create_token(db_session, tg_id, username, scope="d2")
                logger.info(f"API token created by @{username} (tg_id={tg_id})")
                return await render_template(
                    "token.html",
                    active_token=await _active_token_row(db_session, tg_id),
                    new_token=raw,
                )
            if action == "revoke":
                await revoke_active_tokens(db_session, tg_id)
                await db_session.commit()
                logger.info(
                    f"API token revoked by @{userdata.get('username') or tg_id} (tg_id={tg_id})"
                )
                await flash("Токен отозван.", "good")
                return redirect("/token")

        active_token = await _active_token_row(db_session, tg_id)

    return await render_template(
        "token.html", active_token=active_token, new_token=None
    )
