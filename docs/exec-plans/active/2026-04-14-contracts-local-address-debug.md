# contracts-local-address-debug: preserve local test-mode lesson

## Context

We lost time debugging why the contracts page could not auto-fill the current user's address in local `ENVIRONMENT=test`.

The misleading symptom was:

- `Use my address` showed `Could not fill your address automatically.`

The misleading hypothesis was:

- Grist cache was not initialized in `test_mode`

That was not the real production bug.

## Plan changes

1. [x] Confirm local `test_mode` session did inject `TEST_USER_ID`.
2. [x] Confirm temporary Grist cache initialization did not fix the real lookup path.
3. [x] Isolate the actual mismatch in `load_user_from_grist(telegram_id=...)`.
4. [x] Save the lesson in docs with a short repeatable checklist.

## Key finding

The real bug was a type mismatch:

- `grist_cache` indexed `telegram_id` as an `int`
- `load_user_from_grist()` looked it up as `str(telegram_id)`

So the cache lookup missed even when the user existed.

## Verification

- `uv run pytest tests/test_grist_tools.py --no-cov -q`
