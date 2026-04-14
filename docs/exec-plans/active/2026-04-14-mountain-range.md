# mountain-range: show and enforce capture range on contract page

## Context

Mountain contract added a new read-only call:

`fn get_range() -> (i128, i128)`

The current page shows only `message()` and the capture form. It does not surface the valid amount interval and does not validate capture amounts against on-chain range limits.

## Plan changes

1. [x] Add a mountain handler helper that reads `get_range()` and normalizes it for UI and validation.
2. [x] Load range data in the mountain contract detail route and pass it into the template.
3. [x] Show min/max raw values and EURMTL equivalents on the page.
4. [x] Block capture submit when range loading fails on page render.
5. [x] Re-check range server-side in capture prepare and reject out-of-range amounts.
6. [x] Add service and router/template tests for success and failure cases.
7. [x] Run focused pytest coverage for mountain handler and contracts router.

## Risks and Open Questions

- Soroban `returnValueJson` shape for `(i128, i128)` may vary; parsing should be defensive.
- Range limits should be treated as inclusive bounds unless contract behavior proves otherwise.

## Verification

- `uv run pytest tests/services/test_mountain_contract.py tests/routers/test_contracts.py --no-cov -q`
- `just test-fast`
