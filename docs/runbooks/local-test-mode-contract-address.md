# Local Test Mode: Contracts Address Lookup

## Symptom

Local `ENVIRONMENT=test` shows an empty contracts address state:

- the `User address` field stays empty
- `Use my address` shows `Could not fill your address automatically.`

## Fast checks

1. Confirm the page variables are actually empty in DevTools:
   - `prefillUser`
   - `detectedAddress`
2. Confirm local test mode did inject the expected Telegram user:
   - `TEST_USER_ID` is set in `.env`
   - `update_test_user()` puts it into session
3. Do not assume missing Grist initialization is the root cause.

## Real root cause we hit on 2026-04-14

`load_user_from_grist(telegram_id=...)` used the wrong key type for the cache lookup.

- cache index stored `telegram_id` as `int`
- lookup used `str(telegram_id)`

That mismatch caused the user lookup to fail even when:

- the test user was in session
- Grist cache was initialized
- the user existed in Grist

## Where to look

- [other/grist_cache.py](/home/itolstov/Projects/mtl/eurmtl.me/other/grist_cache.py)
- [other/grist_tools.py](/home/itolstov/Projects/mtl/eurmtl.me/other/grist_tools.py)
- [routers/contracts.py](/home/itolstov/Projects/mtl/eurmtl.me/routers/contracts.py)
- [start.py](/home/itolstov/Projects/mtl/eurmtl.me/start.py)

## Repeatable diagnosis

1. Verify whether the failure is page state or lookup state.
   - If `prefillUser` and `detectedAddress` are both empty, the page has no address source.
2. Verify the contracts page is resolving the Telegram user id from session.
3. Verify `load_user_from_grist(telegram_id=...)` uses the same type as the cache index.
4. Only after that investigate Grist initialization.

## Fix

Use `telegram_id` as `int` in the Grist cache lookup path. Do not coerce it to string before calling `find_by_index(..., "telegram_id")`.
