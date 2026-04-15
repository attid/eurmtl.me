# xdr-subinvocation-render: compact contract calls and token transfer summary

## Context

Current `InvokeHostFunction` decoding is verbose and hard to scan:

- separate `Contract`, `Function`, `Arguments` lines
- no compact single-line call view
- no friendly rendering of nested `sub_invocations`
- token contract ids are shown raw instead of readable token names

For Soroban auth trees like `capture(...) -> transfer(...)`, the decoder should surface the meaningful user-facing action directly.

## Plan changes

1. [ ] Add failing XDR parser tests for compact `Contract call: ...` rendering.
2. [ ] Add failing XDR parser tests for `sub_invocations.transfer` summary with amount, source, destination, and token name.
3. [ ] Add a cached token-contract-name resolver based on read-only `name()`.
4. [ ] Render compact linked contract call lines for `InvokeHostFunction`.
5. [ ] Render nested transfer summaries when present in Soroban auth trees.
6. [ ] Run focused parser and Soroban helper tests.

## Display target

- `Contract call: CAFX..SISM.capture(GDLT..AYXI, 12, "message")`
- `Transfer 12 EURMTL from GDLT..AYXI to CAFX..SISM`

## Verification

- `uv run pytest tests/services/test_xdr_parser.py tests/services/test_stellar_soroban.py --no-cov -q`
