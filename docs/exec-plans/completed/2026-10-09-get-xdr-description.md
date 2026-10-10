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

## Коммиты
- `82d2ef4` fix(remote): return transaction description in get_xdr response (push master, CI Docker `37879894372` ✓).

## Прод-верификация (2026-10-09)
- `GET https://eurmtl.me/remote/get_xdr/018941216e191b3b4123535efaa0333b7f4eacc426ecd306436f8eb187f5ce1d` → `{"description": "Исходящий платёж аккаунта GD6TPYDU…", "xdr": …}`.
- `GET https://eurmtl.me/remote/get_xdr/02aef2244a28b1aa4086c1209d68f0c13b1181912b833246deb4220d850fbcbb` → `{"description": "Open EURMTL trustline", "xdr": …}`.
- Оба поля присутствуют, деплой после CI уже на проде.
