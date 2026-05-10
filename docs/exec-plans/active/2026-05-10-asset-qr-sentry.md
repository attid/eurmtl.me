# Asset QR Sentry

## Context

`GET /asset/MTLTask` failed with a Horizon 404 while building a trustline QR URI.
The route currently turns this external/data-quality failure into a 500 response.

## Plan

1. [x] Add focused tests for trustline URI generation without Horizon account loading.
2. [x] Add focused route test for QR generation failure reporting to Sentry without 500.
3. [x] Implement minimal route/service changes.
4. [x] Run focused tests and changed-file checks.

## Verification

- `uv run pytest tests/services/test_stellar_client.py::TestSep7Helpers::test_xdr_to_uri_round_trip_and_add_trust_line_uri -q`
- `uv run pytest tests/routers/test_helpers.py -q`
- `just check-changed`
