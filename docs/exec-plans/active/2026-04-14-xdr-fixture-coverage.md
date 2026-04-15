## Goal

Split the collected `tests/fixtures/xdr/9.txt` bundle into stable per-case fixtures and extend regression coverage for distinct `InvokeHostFunction/sub_invocations` patterns.

## Selected Fixtures

- `mountain_capture_with_transfer.xdr`
- `swap_chained_with_xlm_transfer.xdr`
- `swap_with_usdm_transfer.xdr`
- `swap_chained_with_yusdc_transfer.xdr`
- `deposit_with_dual_transfers.xdr`
- `withdraw_with_unknown_subinvocation.xdr`
- `init_stableswap_pool_with_aqua_transfer.xdr`

## Coverage Goals

- Keep compact `Contract call` rendering stable across different function signatures.
- Keep `Transfer ... (raw)` summaries stable for token and XLM/native flows.
- Keep the warning path stable when nested calls exist but are not yet decoded.
- Ensure real XDR fixtures, not hand-edited ad hoc files, protect against regressions.

## Status

- `deposit_with_dual_transfers.xdr` now explicitly guards both nested `Transfer ...` summaries.
- `withdraw_with_unknown_subinvocation.xdr` no longer hides the nested token burn behind a generic warning:
  decoder renders `Burn ... (raw)` and falls back to `Nested call: contract.fn(...)` for other contract calls.
- Warning remains only for sub-invocations that still cannot be rendered at all.
