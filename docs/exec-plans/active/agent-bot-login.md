# Agent Bot Login

## Контекст
Бот уже подписант мультисига фонда. Нужен машинный логин: сессия на сайте из владения ключом подписанта, без ТГ-флоу. Идентичность = pubkey из Grist (`EURMTL_users`), права = вес в Horizon. `check_user_weight()`, `get_fund_signers()` и гейты /d не меняются.

## Решения (согласованы)
- Nonce в server-side store (не в cookie-сессии): одноразовость честная, TTL 60 с, паттерн `routers/remote_sep07_auth.py`.
- Ответы: GET → `{"nonce": "..."}`; POST → `{"status": "ok"}`; ошибки 400/403 `bad_signature`, `nonce_expired`, `not_a_signer`, `no_grist_user`.
- Роут в `routers/index.py`; путь и схемы добавляются в `openapi.json`.
- `userdata` агента: `{"id": telegram_id, "username": из_grist, "first_name": username}`.

## План изменений
1. [x] `routers/agent_login.py` (новый модуль, blueprint реюзнут из `routers/index.py`): `GET/POST /login/agent` — nonce store (TTL 60 с, max 1000 + cleanup), verify ed25519 подписи ASCII nonce, проверка адреса в `get_fund_signers()`, загрузка Grist-строки, запись `session["userdata"]`/`session["user_id"]`.
2. [x] `start.py`: регистрация `routers.agent_login.blueprint`; `routers/index.py`: `/login/agent` в `openapi.json` paths.
3. [x] `templates/llm.txt`: раздел «Agent login» — nonce → подпись → POST → cookie, формат ошибок, отзыв, пример на Python.
4. [x] `tests/routers/test_agent_login.py`: happy path (сессия + userdata), повтор/просрочка nonce, bad signature, bad address, не-подписант, нет Grist-строки, упоминание в openapi/llms.

## Риски и открытые вопросы
- `stellar_sdk.Keypair.from_public_key(address).verify()` кидает `BadSignatureError` — ловить явно. (Обработано: + `bad_address` на невалидном G-адресе.)

## Верификация
- `UV_CACHE_DIR=/tmp/uv-cache just check-changed`
- `uv run --extra dev pytest tests/routers/test_agent_login.py tests/routers/test_index.py -q`
- Дым: скрипт с генерацией ed25519 ключа, полный флоу GET→POST, потом проверка сессии на защищённом роуте.
