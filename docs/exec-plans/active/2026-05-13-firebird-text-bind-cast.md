# Firebird text bind cast

## Goal

Make `Transactions.body` bind as `BLOB SUB_TYPE TEXT` for Firebird inserts so long XDR values are not truncated through `VARCHAR(2000)`.

## Scope

- Change the transaction text ORM fields that map to Firebird BLOB text columns.
- Add a regression test for Firebird async SQL compilation.
- Do not change the database schema in this task.

## Checks

- Run the new SQL model regression test.
- Run changed-file checks.

## Results

- `uv run --extra dev pytest tests/db/test_sql_models_firebird.py -q --no-cov`: passed, 1 test.
- `uv run --extra dev pytest tests/routers/test_sign_tools.py tests/routers/test_remote.py -q --no-cov`: passed, 16 tests.
- `just check-changed`: passed.
