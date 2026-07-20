# Pool Data Fallback

## Context

`GET /decode/<hash>` can crash while rendering a `LiquidityPoolWithdraw` when Horizon
returns `404` for the pool id. `services.stellar_client.get_pool_data()` catches the
Horizon error, but its fallback constructs `LiquidityPoolAsset(Asset("XLM"), Asset("XLM"))`.
The Stellar SDK rejects that pair, so the fallback raises `ValueError` and the decode
request returns `500`.

## Scope

- Keep `/decode` text rendering resilient when Horizon has no pool data.
- Do not invent liquidity pool assets from a pool id alone.
- Keep the change limited to `get_pool_data()` fallback behavior.
- Add regression coverage for the fallback path.

## Files

- `services/stellar_client.py`
- `tests/services/test_stellar_client.py`

## Verification

- `uv run --extra dev pytest tests/services/test_stellar_client.py::test_get_pool_data_returns_safe_fallback_when_horizon_pool_missing -q --no-cov` - passed.
- `uv run --extra dev pytest tests/services/test_stellar_client.py tests/services/test_xdr_parser.py -q --no-cov` - passed.
- `uv run --extra dev ruff check services/stellar_client.py tests/services/test_stellar_client.py` - passed.
- `uv run --extra dev ruff format --check services/stellar_client.py tests/services/test_stellar_client.py` - passed.
- `just check-changed` - passed.
