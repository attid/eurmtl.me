# Federation Address Admin UI

## Context

`/federation` now uses `t_addresses` as the primary SEP-2 source and falls back to
`t_signers`. There is no web UI to inspect or edit primary `t_addresses` records.

## Scope

- Add an admin-only web page for `t_addresses` list/create/update/delete.
- Keep `t_addresses` as the primary federation source.
- Normalize saved `stellar_address` values to lowercase.
- Add a user dropdown link for known superadmin Telegram IDs.

## Files

- `routers/federal.py`
- `templates/tabler_federation_addresses.html`
- `templates/tabler_base.html`
- `tests/routers/test_federal.py`

## Verification

- Add failing tests before implementation.
- Run focused federal router tests.
- Run changed-file checks.
- `uv run --extra dev pytest tests/routers/test_federal.py -q --no-cov` - passed.
- `just check-changed` - passed.
