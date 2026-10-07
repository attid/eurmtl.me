"""Agent signer login: machine session from multisig key ownership.

GET  /login/agent -> {"nonce": "<hex>"} (single-use, 60 s TTL)
POST /login/agent {"address", "nonce", "signature"} -> session cookie
"""

import base64
import binascii
import secrets
import time

from quart import request, session
from stellar_sdk import Keypair
from stellar_sdk.exceptions import BadSignatureError

from other.grist_tools import load_user_from_grist
from other.web_tools import cors_jsonify
from services.stellar_client import get_fund_signers

from .index import blueprint

AGENT_NONCE_TTL_SECONDS = 60
AGENT_NONCE_MAX_STORE = 1000

# In-process nonce store: {nonce_hex: created_at (monotonic)}
_agent_nonce_store: dict[str, float] = {}


def _agent_error(message: str, status: int):
    return cors_jsonify({"status": "error", "message": message}, status)


def _agent_nonce_cleanup() -> None:
    now = time.monotonic()
    expired = [
        n
        for n, created in _agent_nonce_store.items()
        if now - created > AGENT_NONCE_TTL_SECONDS
    ]
    for n in expired:
        _agent_nonce_store.pop(n, None)
    while len(_agent_nonce_store) > AGENT_NONCE_MAX_STORE:
        _agent_nonce_store.pop(next(iter(_agent_nonce_store)), None)


def _decode_signature(signature: str) -> bytes | None:
    if not signature:
        return None
    try:
        raw = base64.b64decode(signature, validate=True)
        if len(raw) == 64:
            return raw
    except (binascii.Error, ValueError):
        pass
    try:
        raw = bytes.fromhex(signature)
        if len(raw) == 64:
            return raw
    except ValueError:
        pass
    return None


@blueprint.route("/login/agent", methods=("GET",))
async def agent_login_nonce():
    _agent_nonce_cleanup()
    nonce = secrets.token_hex(32)
    _agent_nonce_store[nonce] = time.monotonic()
    return cors_jsonify({"nonce": nonce})


@blueprint.route("/login/agent", methods=("POST",))
async def agent_login_verify():
    data = await request.get_json(silent=True) or {}
    address = data.get("address") or ""
    nonce = data.get("nonce") or ""
    signature = data.get("signature") or ""

    _agent_nonce_cleanup()
    created_at = _agent_nonce_store.pop(nonce, None)
    if created_at is None:
        return _agent_error("nonce_expired", 400)
    if time.monotonic() - created_at > AGENT_NONCE_TTL_SECONDS:
        return _agent_error("nonce_expired", 400)

    try:
        public_key = Keypair.from_public_key(address)
    except Exception:
        return _agent_error("bad_address", 400)

    signature_bytes = _decode_signature(signature)
    if signature_bytes is None:
        return _agent_error("bad_signature", 400)

    try:
        public_key.verify(nonce.encode("ascii"), signature_bytes)
    except BadSignatureError:
        return _agent_error("bad_signature", 400)

    fund_data = await get_fund_signers()
    signers = (fund_data or {}).get("signers", [])
    signer = next((s for s in signers if s.get("key") == address), None)
    if signer is None:
        return _agent_error("not_a_signer", 403)

    user = await load_user_from_grist(account_id=address)
    if user is None:
        return _agent_error("no_grist_user", 403)

    username = (user.username or "").lstrip("@")
    session["userdata"] = {
        "id": str(user.telegram_id),
        "username": username,
        "first_name": username,
    }
    session["user_id"] = str(user.telegram_id)
    return cors_jsonify({"status": "ok"})
