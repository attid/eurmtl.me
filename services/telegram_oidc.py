import base64
import hashlib
import secrets
import time
from typing import Any

import jwt
from jwt import ExpiredSignatureError, InvalidAudienceError, InvalidIssuerError

from other.config_reader import config
from other.web_tools import http_session_manager

TELEGRAM_AUTH_URL = "https://oauth.telegram.org/auth"
TELEGRAM_TOKEN_URL = "https://oauth.telegram.org/token"
TELEGRAM_JWKS_URL = "https://oauth.telegram.org/.well-known/jwks.json"
TELEGRAM_OIDC_ISSUER = "https://oauth.telegram.org"
TELEGRAM_OIDC_SCOPE = "openid profile"


def build_redirect_uri() -> str:
    if config.telegram_login_redirect_uri:
        return config.telegram_login_redirect_uri
    return f"https://{config.domain}/login/telegram/callback"


def generate_token_urlsafe(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def build_pkce_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


async def exchange_telegram_code(code: str, code_verifier: str) -> dict[str, Any]:
    client_id = config.telegram_login_client_id
    client_secret = config.telegram_login_client_secret.get_secret_value()
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    response = await http_session_manager.get_web_request(
        "POST",
        TELEGRAM_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": build_redirect_uri(),
            "client_id": client_id,
            "code_verifier": code_verifier,
        },
        return_type="json",
    )
    if response.status != 200 or not isinstance(response.data, dict):
        raise ValueError(f"Telegram token endpoint returned status {response.status}")
    return response.data


async def fetch_telegram_jwks() -> dict[str, Any]:
    response = await http_session_manager.get_web_request(
        "GET", TELEGRAM_JWKS_URL, return_type="json"
    )
    if response.status != 200 or not isinstance(response.data, dict):
        raise ValueError(f"Telegram JWKS endpoint returned status {response.status}")
    return response.data


def _signing_key_from_jwks(id_token: str, jwks: dict[str, Any]) -> Any:
    header = jwt.get_unverified_header(id_token)
    key_id = header.get("kid")
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == key_id:
            return jwt.PyJWK.from_dict(jwk).key
    raise ValueError("Telegram signing key not found")


async def decode_telegram_id_token(id_token: str, nonce: str) -> dict[str, Any]:
    jwks = await fetch_telegram_jwks()
    signing_key = _signing_key_from_jwks(id_token, jwks)
    claims = jwt.decode(
        id_token,
        signing_key,
        algorithms=["RS256"],
        audience=config.telegram_login_client_id,
        issuer=TELEGRAM_OIDC_ISSUER,
    )
    return validate_oidc_claims(
        claims, client_id=config.telegram_login_client_id, nonce=nonce
    )


def validate_oidc_claims(
    claims: dict[str, Any], *, client_id: str, nonce: str
) -> dict[str, Any]:
    if claims.get("iss") != TELEGRAM_OIDC_ISSUER:
        raise InvalidIssuerError("Invalid issuer")

    audience = claims.get("aud")
    valid_audience = audience == client_id or (
        isinstance(audience, list) and client_id in audience
    )
    if not valid_audience:
        raise InvalidAudienceError("Invalid audience")

    if claims.get("nonce") != nonce:
        raise ValueError("Invalid nonce")

    expires_at = claims.get("exp")
    if not isinstance(expires_at, int) or expires_at <= int(time.time()):
        raise ExpiredSignatureError("Signature has expired")

    return claims


def telegram_claims_to_userdata(claims: dict[str, Any]) -> dict[str, Any]:
    user_id = claims.get("id", claims.get("sub"))
    return {
        "id": user_id,
        "first_name": claims.get("name", ""),
        "last_name": "",
        "username": claims.get("preferred_username"),
        "photo_url": claims.get("picture"),
        "auth_date": claims.get("iat"),
        "hash": None,
    }
