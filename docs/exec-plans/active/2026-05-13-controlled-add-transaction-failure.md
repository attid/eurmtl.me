# Controlled add transaction failure

## Goal

Prevent raw 500 responses when a valid add-transaction request fails during persistence.

## Scope

- `/sign_tools` should keep the user on the add form, preserve entered values, and show a generic failure message.
- `/remote/add_transaction` should return a generic JSON error with HTTP 503.
- Internal exception details must be logged but not shown to users or API clients.

## Checks

- Add route tests for web and API exception paths.
- Run targeted router tests after implementation.

## Results

- `uv run --extra dev pytest tests/routers/test_sign_tools.py tests/routers/test_remote.py -q --no-cov`: passed, 16 tests.
- `just check-changed`: passed.
- `just arch-test`: passed.
- `just check`: blocked by existing formatting drift in unrelated files.
