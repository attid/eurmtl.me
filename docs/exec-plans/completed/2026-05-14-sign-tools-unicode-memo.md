# Sign tools Unicode memo

## Goal

Allow `Insert Memo Into XDR` on `/sign_tools` to accept Cyrillic text, spaces, and punctuation while preserving Stellar text memo limits.

## Scope

1. [x] Update server validation for `/lab/update_memo`.
2. [x] Update client validation in `templates/tabler_sign_add.html`.
3. [x] Add/update regression tests for Cyrillic memo and byte-length validation.
4. [x] Run focused tests and changed-file checks.

## Constraints

- Keep XDR update behavior unchanged: replace or add `TextMemo`.
- Preserve Stellar text memo maximum: 28 UTF-8 bytes.
- Keep control characters rejected.

## Verification

- RED: updated memo tests failed against the old ASCII-only validation.
- `uv run --extra dev pytest tests/routers/test_laboratory.py::test_lab_update_memo_rejects_invalid_memo_length tests/routers/test_laboratory.py::test_lab_update_memo_rejects_memo_over_28_bytes tests/routers/test_laboratory.py::test_lab_update_memo_rejects_control_characters tests/routers/test_laboratory.py::test_lab_update_memo_accepts_cyrillic_spaces_and_punctuation -q --no-cov`: passed, 4 tests.
- `uv run --extra dev pytest tests/routers/test_laboratory.py -q --no-cov`: passed, 18 tests.
- `uv run python - <<'PY' ...`: confirmed `update_memo_in_xdr()` round-trips `Привет!`.
- `just check-changed`: passed.
