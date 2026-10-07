# Agent Bot Login

## Контекст
Бот уже подписант мультисига фонда. Нужен машинный логин: сессия на сайте из владения ключом, без ТГ-флоу, 1в1 как у людей: идентичность = pubkey из Grist (`EURMTL_users`, непустой telegram_id), права на действия проверяются отдельно каждым действием (`check_user_weight()` на публикации и т.п.). Мультисиг на входе НЕ проверяется. `check_user_weight()`, `get_fund_signers()` и гейты /d не меняются.

## Решения (согласованы)
- Nonce в server-side store (не в cookie-сессии): одноразовость честная, TTL 60 с, паттерн `routers/remote_sep07_auth.py`.
- Ответы: GET → `{"nonce": "..."}`; POST → `{"status": "ok"}`; ошибки 400 `bad_signature`/`nonce_expired`/`bad_address`, 403 `no_grist_user`.
- Роут в `routers/index.py`; путь и схемы добавляются в `openapi.json`.
- `userdata` агента: `{"id": telegram_id, "username": из_grist, "first_name": username}`.

## План изменений
1. [x] `routers/agent_login.py` (новый модуль, собственный blueprint `agent_login`, зарегистрирован в `start.py` и `tests/fixtures/app.py`): `GET/POST /login/agent` — nonce store (TTL 60 с, max 10000 + cleanup), verify ed25519 подписи ASCII nonce, загрузка Grist-строки (с непустым telegram_id), запись `session["userdata"]`/`session["user_id"]`.
2. [x] `start.py`: регистрация `routers.agent_login.blueprint`; `routers/index.py`: `/login/agent` в `openapi.json` paths.
3. [x] `templates/llm.txt`: раздел «Agent login» — nonce → подпись → POST → cookie, формат ошибок, пример на Python.
4. [x] `tests/routers/test_agent_login.py`: happy path (сессия + userdata), повтор/просрочка nonce, bad signature, bad address, нет Grist-строки, упоминание в openapi/llms.

## Ревью (2026-10-08)
- agy, 2 круга, отчёт `docs/drafts/agy_agent_login_review.md`; фикс-коммит `b42da1c`.
- Уточнение владельца: логин 1в1 как телега — гейт `not_a_signer` (вес в мультисиге на входе) убран, доступ к логину = строка в Grist. Коммит после правки.

## Риски и открытые вопросы
- `stellar_sdk.Keypair.from_public_key(address).verify()` кидает `BadSignatureError` — ловить явно. (Обработано: + `bad_address` на невалидном G-адресе.)

## Верификация
- `uv run --extra dev pytest tests/routers/test_agent_login.py -q` → 9 passed.
- `uv run --extra dev pytest tests -q` → 450 passed, 2 failed — пре-существующие фейлы `tests/routers/test_decision.py` (шаблоны `d2_frag_edit.html`/`d2_frag_new.html` отсутствуют в репо, `routers/decision.py:204` → 500), воспроизводятся на чистом HEAD, к задаче не относятся.
- `ruff check` + `ruff format --check` на изменённых файлах — чисто.
- Дым (вне репо): GET nonce → ed25519 подпись (base64 и hex) → POST → сессия (`user_id`/`userdata`) на защищённом роуте → повторный POST с тем же nonce → 400 `nonce_expired`. PASS.
- Commit: `e735029 feat: add machine login for multisig signer agents` (ветка `attid/feat-agent-bot-login`, не запушен).
