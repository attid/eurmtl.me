import hashlib
import json
import os
import signal
import subprocess
import uuid

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
)

from other.config_reader import config, start_path
from db.sql_models import Signers
from services.stellar_client import check_user_weight
from other.telegram_tools import check_response
from other.quart_tools import get_ip
from other.tailscale import get_latest_version_package
from loguru import logger

blueprint = Blueprint("index", __name__)


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

        async with current_app.db_pool() as db_session:
            result = await db_session.execute(
                select(Signers).filter(Signers.username == data["username"])
            )
            user = result.scalars().first()
            if user and user.tg_id != data["id"]:
                user.tg_id = data["id"]
                await db_session.commit()

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
