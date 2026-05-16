# SEP-2 Federation Not Found Response

## Context

StellarExpert reports `FEDERATION_SERVER ignored` for `eurmtl.me`. Manual checks show
`/federation/?q=...&type=...` returns `200 OK` with `{"error":"Not found."}` for missing
records and does not include `Access-Control-Allow-Origin: *` on that response.
After the status/CORS fix, the endpoint still sets a session cookie on each public
lookup and does not explicitly send no-cache headers.

SEP-2 requires federation responses to include CORS. For missing records it requires
`404 Not Found`; every other HTTP status code for that case is treated as an error.
SEP-2 also says federation responses should not be cached.

## Scope

- Update `/federation` fallback behavior only.
- Keep successful federation lookup JSON unchanged.
- Add focused test coverage for missing federation records.
- Avoid session cookies for public federation lookups.
- Add explicit no-cache headers to federation responses.
- Use `t_signers` as a fallback federation source when `t_addresses` has no match.
- Normalize fallback signer usernames to lowercase Stellar addresses.

## Files

- `routers/federal.py`
- `tests/routers/test_federal.py`

## Verification

- `uv run --extra dev pytest tests/routers/test_federal.py -q --no-cov` - passed.
- `just check-changed` - passed.
- `uv run --extra dev pytest tests/routers/test_federal.py -q --no-cov` - passed
  after adding no-cache/no-cookie coverage.
- `just check-changed` - passed after adding no-cache/no-cookie coverage.
- `uv run --extra dev pytest tests/routers/test_federal.py -q --no-cov` - passed
  after adding signer fallback coverage.
