# telegram-oidc-login: Replace Telegram widget login

## Context

The `/login` page still exposes the legacy Telegram widget flow. It asks for a
phone number in a Telegram iframe and sends users through `/authorize`.

Goal: keep bot login and hidden `/authorize` compatibility, but replace the
visible second login option with Telegram OpenID Connect Authorization Code Flow
with PKCE.

## Plan changes

1. [x] Add Telegram OIDC configuration fields.
2. [x] Add focused tests for the login page, OIDC redirect, callback failures,
   callback success, `return_to`, PKCE, and claims validation.
3. [x] Add OIDC helper for PKCE, token exchange, JWKS JWT validation, and
   claim-to-session mapping.
4. [x] Add `/login/telegram` and `/login/telegram/callback` routes.
5. [x] Replace the legacy widget block in `templates/tabler_login.html`.
6. [x] Add ADR for `PyJWT[crypto]`.
7. [x] Run focused tests and changed-file checks.

## Risks and Open Questions

- Production requires BotFather Allowed URL:
  `https://eurmtl.me/login/telegram/callback`.
- Token/JWT failures must log enough context for diagnosis without token or
  secret leakage.

## Verification

- `uv run pytest tests/routers/test_index.py -q --no-cov`
- `uv run pytest tests/test_telegram_oidc_helpers.py tests/routers/test_telegram_oidc.py -q --no-cov`
- `just lint`
- `just check-changed`
