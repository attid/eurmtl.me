import base64
import hashlib
import time

import pytest
from jwt import ExpiredSignatureError, InvalidAudienceError, InvalidIssuerError

from services.telegram_oidc import (
    TELEGRAM_OIDC_ISSUER,
    build_pkce_challenge,
    validate_oidc_claims,
)


def test_build_pkce_challenge_is_base64url_sha256_without_padding():
    verifier = "abc123_verifier"
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    assert build_pkce_challenge(verifier) == expected
    assert "=" not in build_pkce_challenge(verifier)


def test_validate_oidc_claims_accepts_required_telegram_claims():
    claims = {
        "iss": TELEGRAM_OIDC_ISSUER,
        "aud": "client-id",
        "nonce": "nonce",
        "exp": int(time.time()) + 60,
        "sub": "telegram-sub",
    }

    assert validate_oidc_claims(claims, client_id="client-id", nonce="nonce") == claims


def test_validate_oidc_claims_rejects_wrong_issuer():
    claims = {
        "iss": "https://example.test",
        "aud": "client-id",
        "nonce": "nonce",
        "exp": int(time.time()) + 60,
    }

    with pytest.raises(InvalidIssuerError):
        validate_oidc_claims(claims, client_id="client-id", nonce="nonce")


def test_validate_oidc_claims_rejects_wrong_audience():
    claims = {
        "iss": TELEGRAM_OIDC_ISSUER,
        "aud": "other-client",
        "nonce": "nonce",
        "exp": int(time.time()) + 60,
    }

    with pytest.raises(InvalidAudienceError):
        validate_oidc_claims(claims, client_id="client-id", nonce="nonce")


def test_validate_oidc_claims_rejects_wrong_nonce():
    claims = {
        "iss": TELEGRAM_OIDC_ISSUER,
        "aud": "client-id",
        "nonce": "other-nonce",
        "exp": int(time.time()) + 60,
    }

    with pytest.raises(ValueError, match="Invalid nonce"):
        validate_oidc_claims(claims, client_id="client-id", nonce="nonce")


def test_validate_oidc_claims_rejects_expired_token():
    claims = {
        "iss": TELEGRAM_OIDC_ISSUER,
        "aud": "client-id",
        "nonce": "nonce",
        "exp": int(time.time()) - 1,
    }

    with pytest.raises(ExpiredSignatureError):
        validate_oidc_claims(claims, client_id="client-id", nonce="nonce")
