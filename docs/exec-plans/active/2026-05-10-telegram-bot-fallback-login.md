# Telegram Bot Fallback Login

## Goal

Add a fallback Telegram login flow through the external `myMTLBot` without running a bot process on `eurmtl.me`.

## Scope

- Keep the primary Telegram OIDC login unchanged.
- Create one-time DB-backed login tokens for `/login/bot`.
- Let `myMTLBot` confirm tokens through `POST /login/bot/confirm` using `Authorization: Bearer <EURMTL_KEY>`.
- Let the browser poll `/login/bot/status/<token>` until success, expiration, or timeout.
- Do not implement avatar caching in this change.

## Files

- Modify `db/sql_models.py` to add `BotLoginToken`.
- Modify `routers/index.py` to add token creation, confirmation, status polling, and session finalization.
- Modify `templates/tabler_login.html` to link to `/login/bot`.
- Add `templates/tabler_bot_login.html` for the polling page.
- Add `tests/routers/test_telegram_bot_login.py` for route behavior.
- Update `tests/routers/test_telegram_oidc.py` if the login page assertions need the new fallback link.

## Test Plan

1. Add focused failing tests for `/login`, `/login/bot`, `/login/bot/confirm`, and `/login/bot/status/<token>`.
2. Run `uv run pytest tests/routers/test_telegram_bot_login.py -q` and verify the new tests fail before implementation.
3. Implement the minimal model, route, and template changes.
4. Run focused tests:
   - `uv run pytest tests/routers/test_telegram_bot_login.py -q`
   - `uv run pytest tests/routers/test_index.py -q`
5. Run repository checks:
   - `just lint`
   - `just check-changed`

## Notes

- Token prefix for Telegram deep links is `eurmtl_`.
- Token TTL is 5 minutes.
- Tokens are single-use: successful browser session creation marks the token `used`.
- Token state lives in the database, not the session.
- `/authorize` remains as a hidden legacy endpoint.
