# 2026-10-09 — get_xdr: вернуть description

## Проблема
`GET /remote/get_xdr/<hash>` отдаёт только `{"xdr": ...}`. Описание транзакции хранится в БД (`transactions.description`, NOT NULL, db/sql_models.py:43), показывается на странице sign_tools, но в API-ответ не попадает. Клиенты (бот mmwb_bot, `bot/other/stellar_tools.py`) не могут получить описание транзакции.

## Изменения
- `routers/remote.py` — `remote_get_xdr`: добавить `"description": transaction.description` в jsonify.
- `tests/routers/test_remote.py` — `test_remote_get_xdr`: задать `mock_tx.description`, ассерт обоих полей.
- `templates/llm.txt` — описать `description` в ответе эндпоинта.

## Проверка
- `just check-changed` — passed.
- `just lint` — passed; `just types` (pyright) — 0 errors; `just arch-test` — passed.
- `just test-fast` — 464 passed (включая `test_remote_get_xdr` с `description`).
