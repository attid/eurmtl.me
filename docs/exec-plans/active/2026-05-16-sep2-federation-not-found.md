# SEP-2 Federation Not Found Response

## Context

StellarExpert reports `FEDERATION_SERVER ignored` for `eurmtl.me`. Manual checks show
`/federation/?q=...&type=...` returns `200 OK` with `{"error":"Not found."}` for missing
records and does not include `Access-Control-Allow-Origin: *` on that response.

SEP-2 requires federation responses to include CORS. For missing records it requires
`404 Not Found`; every other HTTP status code for that case is treated as an error.

## Scope

- Update `/federation` fallback behavior only.
- Keep successful federation lookup JSON unchanged.
- Add focused test coverage for missing federation records.

## Files

- `routers/federal.py`
- `tests/routers/test_federal.py`

## Verification

- `uv run --extra dev pytest tests/routers/test_federal.py -q --no-cov` - passed.
- `just check-changed` - passed.
