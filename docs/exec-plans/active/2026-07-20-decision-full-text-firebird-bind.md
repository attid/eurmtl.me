# Decision Full Text Firebird Bind

## Context

Creating decision 683 published a Telegram post, but `POST /decision` failed when
inserting `t_decisions`. Firebird reported string truncation:
`expected length 2000, actual 2598`.

The ORM model currently declares `Decisions.full_text` as `Text(12000)`, but the
Firebird async dialect compiles inserts with `CAST(:full_text AS VARCHAR(2000))`.
The database schema should not need a migration; this task aligns the ORM bind type
with existing long text fields such as `Transactions.body`.

## Scope

- Change only the ORM type used for `Decisions.full_text` binding.
- Add Firebird SQL compilation regression coverage for `t_decisions`.
- Do not change production database schema.

## Files

- `db/sql_models.py`
- `tests/db/test_sql_models_firebird.py`

## Verification

- `uv run --extra dev pytest tests/db/test_sql_models_firebird.py::test_decisions_full_text_binds_as_firebird_text_blob -q --no-cov` - failed before the model change with `CAST(:full_text AS VARCHAR(2000))`.
- `uv run --extra dev pytest tests/db/test_sql_models_firebird.py -q --no-cov` - passed.
- `uv run --extra dev ruff format --check db/sql_models.py tests/db/test_sql_models_firebird.py` - passed.
- `uv run --extra dev ruff check db/sql_models.py tests/db/test_sql_models_firebird.py` - passed.
- `just check-changed` - passed.
