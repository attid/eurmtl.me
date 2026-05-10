import hashlib
import json
import os
import signal
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import select
from quart import (
    Blueprint,
    Response,
    make_response,
    send_file,
    request,
    session,
    redirect,
    render_template,
    current_app,
    jsonify,
)

from other.config_reader import config, start_path
from db.sql_models import BotLoginToken, Signers
from services.stellar_client import check_user_weight
from services.telegram_oidc import (
    TELEGRAM_AUTH_URL,
    TELEGRAM_OIDC_SCOPE,
    build_pkce_challenge,
    build_redirect_uri,
    decode_telegram_id_token,
    exchange_telegram_code,
    generate_token_urlsafe,
    telegram_claims_to_userdata,
)
from other.telegram_tools import check_response
from other.quart_tools import get_ip
from other.tailscale import get_latest_version_package
from loguru import logger

blueprint = Blueprint("index", __name__)

TELEGRAM_OIDC_STATE_KEY = "telegram_oidc_state"
TELEGRAM_OIDC_NONCE_KEY = "telegram_oidc_nonce"
TELEGRAM_OIDC_VERIFIER_KEY = "telegram_oidc_code_verifier"
BOT_LOGIN_SESSION_KEY = "bot_login_token"
BOT_LOGIN_PREFIX = "eurmtl_"
BOT_LOGIN_TTL_SECONDS = 5 * 60


def _absolute_url(path: str) -> str:
    base_url = request.url_root.rstrip("/")
    if path == "/":
        return f"{base_url}/"
    return f"{base_url}{path}"


def _sitemap_paths() -> list[str]:
    return [
        "/",
        "/llms.txt",
        "/robots.txt",
        "/sitemap.xml",
        "/healthz",
        "/openapi.json",
        "/.well-known/stellar.toml",
        "/.well-known/api-catalog",
        "/.well-known/agent-skills/index.json",
        "/.well-known/agent-skills/eurmtl-http/SKILL.md",
        "/federation",
        "/sep6/info",
        "/lab",
        "/contracts",
    ]


async def _update_signer_tg_id(username: str | None, tg_id: int | str | None) -> None:
    if not username or tg_id is None:
        return

    async with current_app.db_pool() as db_session:
        result = await db_session.execute(
            select(Signers).filter(Signers.username == username)
        )
        user = result.scalars().first()
        if user and user.tg_id != tg_id:
            user.tg_id = tg_id
            await db_session.commit()


def _clear_telegram_oidc_session() -> None:
    session.pop(TELEGRAM_OIDC_STATE_KEY, None)
    session.pop(TELEGRAM_OIDC_NONCE_KEY, None)
    session.pop(TELEGRAM_OIDC_VERIFIER_KEY, None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    return expires_at <= _utcnow()


def _normalize_bot_token(token: str | None) -> str:
    if not token:
        return ""
    if token.startswith(BOT_LOGIN_PREFIX):
        return token[len(BOT_LOGIN_PREFIX) :]
    return token


def _bot_userdata_from_payload(payload: dict) -> dict:
    return {
        "id": payload.get("id"),
        "first_name": payload.get("first_name", ""),
        "last_name": payload.get("last_name", ""),
        "username": payload.get("username"),
        "photo_url": payload.get("photo_url"),
        "auth_date": payload.get("auth_date"),
        "hash": None,
    }


async def _finalize_telegram_login(userdata: dict) -> str:
    session["userdata"] = userdata
    session["user_id"] = userdata["id"]
    await _update_signer_tg_id(userdata.get("username"), userdata.get("id"))
    return session.get("return_to", None) or "/lab"


@blueprint.route("/tailscale", methods=("GET", "POST"))
@blueprint.route("/ts", methods=("GET", "POST"))
@blueprint.route("/ts.deb", methods=("GET", "POST"))
async def tailscale_static_redirect_route():
    try:
        file_name = await get_latest_version_package()
        if file_name:
            # Ensure the file exists in the static directory after the call
            static_file_path = os.path.join(start_path, "static", file_name)
            if os.path.exists(static_file_path):
                # Redirect to the static file URL
                return redirect(f"/static/{file_name}", code=302)
            else:
                logger.error(
                    f"File {file_name} not found in static directory after get_latest_version_package call: {static_file_path}"
                )
                return "File not found on server after check.", 404
        else:
            return "Could not retrieve package information.", 500
    except Exception as e:
        logger.info(f"Error in /tailscale static redirect route: {e}")
        return f"An error occurred: {e}", 500


@blueprint.route("/")
async def cmd_index():
    response = await make_response(await render_template("index.html"))
    response.headers["Link"] = ", ".join(
        [
            '</.well-known/api-catalog>; rel="api-catalog"',
            '</llms.txt>; rel="service-doc"; type="text/plain"',
            '</.well-known/stellar.toml>; rel="service-desc"; type="text/plain"',
            '</.well-known/agent-skills/index.json>; rel="describedby"; type="application/json"',
        ]
    )
    return response


@blueprint.route("/llms.txt")
async def llm_txt():
    return Response(await render_template("llm.txt"), mimetype="text/plain")


@blueprint.route("/robots.txt")
async def robots_txt():
    return Response(
        await render_template("robots.txt", sitemap_url=_absolute_url("/sitemap.xml")),
        mimetype="text/plain",
    )


@blueprint.route("/sitemap.xml")
async def sitemap_xml():
    urls = [_absolute_url(path) for path in _sitemap_paths()]
    return Response(
        await render_template("sitemap.xml", urls=urls), mimetype="application/xml"
    )


@blueprint.route("/healthz")
async def healthz():
    return Response('{"status":"ok"}', mimetype="application/json")


@blueprint.route("/openapi.json")
async def openapi_json():
    base_url = _absolute_url("/")
    document = {
        "openapi": "3.1.0",
        "info": {
            "title": "EURMTL Machine API",
            "version": "1.0.0",
            "description": "Machine-oriented subset of EURMTL HTTP endpoints.",
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/llms.txt": {
                "get": {
                    "summary": "Machine-readable overview for agents",
                    "responses": {"200": {"description": "Plain text guide"}},
                }
            },
            "/remote/decode": {
                "post": {
                    "summary": "Decode Stellar XDR from JSON body",
                    "responses": {
                        "200": {"description": "Decoded XDR"},
                        "400": {"description": "Invalid input"},
                    },
                }
            },
            "/remote/sep07/auth/init": {
                "post": {
                    "summary": "Initialize SEP-7 auth flow",
                    "responses": {
                        "200": {"description": "Flow initialized"},
                        "400": {"description": "Invalid input"},
                    },
                }
            },
            "/lab/build_xdr": {
                "post": {
                    "summary": "Build Stellar transaction XDR from structured JSON",
                    "responses": {
                        "200": {"description": "Built XDR"},
                        "400": {"description": "Invalid input"},
                    },
                }
            },
            "/.well-known/stellar.toml": {
                "get": {
                    "summary": "Stellar ecosystem metadata",
                    "responses": {"200": {"description": "Stellar TOML"}},
                }
            },
        },
    }
    return Response(json.dumps(document, indent=2), mimetype="application/json")


@blueprint.route("/.well-known/api-catalog")
async def api_catalog():
    document = {
        "linkset": [
            {
                "anchor": _absolute_url("/"),
                "service-doc": [{"href": _absolute_url("/llms.txt")}],
                "service-desc": [{"href": _absolute_url("/openapi.json")}],
                "status": [{"href": _absolute_url("/healthz")}],
            }
        ]
    }
    return Response(
        json.dumps(document, indent=2),
        content_type='application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"',
    )


@blueprint.route("/.well-known/agent-skills/eurmtl-http/SKILL.md")
async def published_skill():
    return Response(
        await render_template("eurmtl_http_skill.md"), mimetype="text/markdown"
    )


@blueprint.route("/.well-known/agent-skills/index.json")
async def agent_skills_index():
    skill_body = await render_template("eurmtl_http_skill.md")
    skill_digest = f"sha256:{hashlib.sha256(skill_body.encode('utf-8')).hexdigest()}"
    document = {
        "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
        "skills": [
            {
                "name": "eurmtl-http",
                "type": "skill-md",
                "description": "Use when an agent needs the public EURMTL HTTP routes, machine entrypoints, and request patterns without relying on browser-only pages.",
                "url": "/.well-known/agent-skills/eurmtl-http/SKILL.md",
                "digest": skill_digest,
            }
        ],
    }
    return Response(json.dumps(document, indent=2), mimetype="application/json")


@blueprint.route("/mytest", methods=("GET", "POST"))
async def cmd_mytest():
    return "***"


@blueprint.route("/uuid", methods=("GET", "POST"))
async def get_uid():
    return uuid.uuid4().hex


@blueprint.route("/err", methods=("GET", "POST"))
@blueprint.route("/log", methods=("GET", "POST"))
async def cmd_send_err():
    if (await check_user_weight()) > 0:
        file_name = "/home/eurmtl/hypercorn.log"
        import os

        if os.path.isfile(file_name):
            return await send_file(file_name, mimetype="text/plain")
            # with open(file_name, "r") as f:
            #    text = f.read()
        else:
            return "No error"
    else:
        return "need authority"


@blueprint.route("/restart", methods=("GET", "POST"))
async def restart():
    if request.method == "POST":
        # надо проверить параметр если
        # body: JSON.stringify({type: 'cache'})
        json_data = await request.get_json()
        cache_refresh = json_data and json_data.get("type") == "cache"

        if (await check_user_weight()) > 0:
            username = "@" + session["userdata"]["username"]
            if username.lower() == "@itolstov":
                if cache_refresh:
                    from quart import current_app

                    current_app.jinja_env.cache = {}
                    return "Cache refreshed"
                else:
                    cmd = f"/usr/bin/ps -o ppid= -p {os.getpid()}"
                    result = subprocess.run(cmd.split(), stdout=subprocess.PIPE)
                    parent_pid = int(result.stdout.decode("utf-8").strip())

                    # Отправить сигнал SIGTERM родительскому процессу
                    os.kill(parent_pid, signal.SIGTERM)

                    return "Restarting..."
        else:
            return "need authority", 403
    else:
        return await render_template("tabler_restart.html")


@blueprint.route("/authorize")
async def authorize():
    data = {
        "id": request.args.get("id", None),
        "first_name": request.args.get("first_name", None),
        "last_name": request.args.get("last_name", None),
        "username": request.args.get("username", None),
        "photo_url": request.args.get("photo_url", None),
        "auth_date": request.args.get("auth_date", None),
        "hash": request.args.get("hash", None),
    }
    if (
        check_response(data, config.skynet_token.get_secret_value())
        and data["username"]
    ):
        # Authorize user
        session["userdata"] = data
        session["user_id"] = data["id"]

        await _update_signer_tg_id(data["username"], data["id"])

        return_to_url = session.get("return_to", None)
        if return_to_url:
            return redirect(return_to_url)
        else:
            return redirect("/lab")
    else:
        return "Authorization failed"


@blueprint.route("/login")
async def login():
    return await render_template("tabler_login.html")


@blueprint.route("/login/bot")
async def login_bot():
    token = generate_token_urlsafe(32)
    now = _utcnow()
    expires_at = now + timedelta(seconds=BOT_LOGIN_TTL_SECONDS)
    login_token = BotLoginToken(
        token=token,
        status="pending",
        return_to=session.get("return_to", None),
        created_at=now,
        expires_at=expires_at,
    )

    async with current_app.db_pool() as db_session:
        db_session.add(login_token)
        await db_session.commit()

    session[BOT_LOGIN_SESSION_KEY] = token
    bot_url = f"https://t.me/myMTLBot?start={BOT_LOGIN_PREFIX}{token}"
    return await render_template(
        "tabler_bot_login.html",
        token=token,
        bot_url=bot_url,
        ttl_seconds=BOT_LOGIN_TTL_SECONDS,
    )


@blueprint.route("/login/bot/confirm", methods=("POST",))
async def login_bot_confirm():
    api_key = request.headers.get("Authorization", "")
    if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
        return jsonify({"status": "error", "message": "unauthorized"}), 401

    payload = await request.get_json(silent=True) or {}
    token = _normalize_bot_token(payload.get("token"))
    if not token or not payload.get("id"):
        return jsonify({"status": "error", "message": "invalid_payload"}), 400

    async with current_app.db_pool() as db_session:
        login_token = await db_session.get(BotLoginToken, token)
        if not login_token or login_token.status != "pending":
            return jsonify({"status": "error", "message": "invalid_token"}), 400

        if _is_expired(login_token.expires_at):
            login_token.status = "expired"
            await db_session.commit()
            return jsonify({"status": "error", "message": "expired"}), 400

        userdata = _bot_userdata_from_payload(payload)
        login_token.userdata_json = json.dumps(userdata, ensure_ascii=False)
        login_token.status = "confirmed"
        login_token.confirmed_at = _utcnow()
        await db_session.commit()

    return jsonify({"status": "ok"})


@blueprint.route("/login/bot/status/<token>")
async def login_bot_status(token: str):
    session_token = session.get(BOT_LOGIN_SESSION_KEY)
    if not session_token or session_token != token:
        return jsonify({"status": "error", "message": "forbidden"}), 403

    async with current_app.db_pool() as db_session:
        login_token = await db_session.get(BotLoginToken, token)
        if not login_token:
            return jsonify({"status": "error", "message": "not_found"}), 404

        if login_token.status in {"pending", "confirmed"} and _is_expired(
            login_token.expires_at
        ):
            login_token.status = "expired"
            await db_session.commit()
            return jsonify({"status": "expired"})

        if login_token.status == "pending":
            return jsonify({"status": "pending"})

        if login_token.status == "expired":
            return jsonify({"status": "expired"})

        if login_token.status != "confirmed" or not login_token.userdata_json:
            return jsonify({"status": login_token.status})

        userdata = json.loads(login_token.userdata_json)
        redirect_url = await _finalize_telegram_login(userdata)
        login_token.status = "used"
        login_token.used_at = _utcnow()
        await db_session.commit()
        session.pop(BOT_LOGIN_SESSION_KEY, None)

    return jsonify({"status": "confirmed", "redirect": redirect_url})


@blueprint.route("/login/telegram")
async def login_telegram():
    state = generate_token_urlsafe()
    nonce = generate_token_urlsafe()
    code_verifier = generate_token_urlsafe(48)
    code_challenge = build_pkce_challenge(code_verifier)

    session[TELEGRAM_OIDC_STATE_KEY] = state
    session[TELEGRAM_OIDC_NONCE_KEY] = nonce
    session[TELEGRAM_OIDC_VERIFIER_KEY] = code_verifier

    query = urlencode(
        {
            "client_id": config.telegram_login_client_id,
            "redirect_uri": build_redirect_uri(),
            "response_type": "code",
            "scope": TELEGRAM_OIDC_SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return redirect(f"{TELEGRAM_AUTH_URL}?{query}")


@blueprint.route("/login/telegram/callback")
async def login_telegram_callback():
    expected_state = session.get(TELEGRAM_OIDC_STATE_KEY)
    actual_state = request.args.get("state")
    if not expected_state or actual_state != expected_state:
        return "Invalid Telegram login state", 400

    code = request.args.get("code")
    if not code:
        return "Missing Telegram login code", 400

    nonce = session.get(TELEGRAM_OIDC_NONCE_KEY)
    code_verifier = session.get(TELEGRAM_OIDC_VERIFIER_KEY)
    if not nonce or not code_verifier:
        return "Telegram login session expired", 400

    try:
        token_response = await exchange_telegram_code(code, code_verifier)
        id_token = token_response.get("id_token")
        if not id_token:
            raise ValueError("Telegram token response does not include id_token")
        claims = await decode_telegram_id_token(id_token, nonce)
    except Exception as exc:
        logger.warning(f"Telegram OIDC login failed: {type(exc).__name__}: {exc}")
        return "Telegram authorization failed", 400

    userdata = telegram_claims_to_userdata(claims)
    _clear_telegram_oidc_session()

    return redirect(await _finalize_telegram_login(userdata))


@blueprint.route("/addr")
async def lab_addr():
    return await render_template("tabler_addr.html")


@blueprint.route("/logout")
async def logout():
    session.pop("userdata", None)
    session.pop("user_id", None)
    return redirect("/lab")


@blueprint.route("/verification")
async def verification():
    return await render_template("verification.html")


@blueprint.route("/bor", methods=("GET", "POST"))
@blueprint.route("/bsn", methods=("GET", "POST"))
@blueprint.route("/bsn/", methods=("GET", "POST"))
@blueprint.route("/bsn/<account_id>", methods=("GET", "POST"))
async def get_bsn(account_id: str = ""):
    return await render_template("bsn.html", account_id=account_id)


@blueprint.route("/myip")
async def myip():
    return await get_ip()
