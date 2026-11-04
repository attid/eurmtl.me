# API-токены (персональные) и MCP-эндпоинт для агентов

Создан 2026-11-04. Контекст: владелец хочет, чтобы AI-агенты могли работать
с d2 (вопросы eurmtl.me) — создание и правка черновиков — от имени
конкретного человека. Прожарка (grilling) проведена 2026-11-04, все
решения зафиксированы владельцем (см. «Решения»).

## Проблема

- Доступ к d2 у веба — через Telegram-сессию; агент сессией жить не умеет.
- Токены в Grist хранить нельзя: док читают все подписанты, любой может
  скопировать чужой токен и действовать от чужого имени.
- Прецедент хранения секретов в собственной БД есть: `t_bot_login_tokens`.

## Решения (прожарка 2026-11-04)

1. Токен живёт **вечно**, отзыв/перевыпуск вручную (без TTL).
2. **Один активный токен на юзера**: создание нового автоматически
   отзывает старый (ротация = просто создать новый).
3. Scope — **один гранул `d2`** (без разбивки read/write/publish).
   Publish — фаза 2, отдельным гранулом `d2_publish`.
4. MCP-транспорт — **минимальный stateless JSON-RPC 2.0 POST**: без SSE,
   без сессий, без rate limit (токен 128 бит, перебор бессмыслен).
   Клиенты — скилы агентов; протокол MCP как таковой не используется,
   описания tools пишутся как документация для памяти агента.
5. Страница `/token` доступна **любому залогиненному**; ссылка в меню,
   где «logout» (не в шапку).
6. Аудит — **только loguru**, отдельной таблицы нет (след в Grist: CREATED_BY).
7. Username — **снапшот** на момент создания токена (ник меняется —
   CREATED_BY останется старым; перевыпуск обновит).
8. Org — **явный параметр каждого tool** (+ tool `d2_list_orgs`).
9. Номер вопроса — **опционален**, авто = max+1 по орге
   (`_org_next_number`); явный дубликат отклоняется как в вебе.
10. Название таблицы **нейтральное** (`t_api_tokens`, класс `ApiToken`) —
    без «d2» в имени: доступ сайт-wide, d2 лишь первый потребитель.

## Дизайн

### Таблица `t_api_tokens` (db/sql_models.py, класс ApiToken)

| колонка    | тип           | notes                                  |
|------------|---------------|----------------------------------------|
| token_hash | String(64) PK | sha256 hex от токена; сам токен НЕ храним |
| tg_id      | BigInteger    | не NULL                                 |
| username   | String(64)    | снапшот, без «@»                        |
| scope      | String(255)   | гранулы через запятую, сейчас "d2"      |
| created_at | DateTime      | UTC                                     |
| revoked_at | DateTime NULL | NULL = активный                         |

- Токен: `secrets.token_hex(16)` → 32 hex. Показывается **один раз**
  при создании, потом недоступен даже владельцу.
- «Один активный»: при вставке нового — `UPDATE ... SET revoked_at=now()
  WHERE tg_id=? AND revoked_at IS NULL`.
- Схема создаётся автоматически: `Base.metadata.create_all`
  (start.py `/updatedb` и создание пула; существующие таблицы не трогает).

### Страница `/token` (routers/token.py, templates/token.html)

- GET: без сессии → редирект на логин (паттерн остальных роутов).
  Карточка: активный токен? дата создания / отозван когда; кнопки
  «Создать» или «Перевыпустить»+«Отозвать» (с confirm — старый умирает
  сразу, агент с ним отвалится).
- POST `/token/create` — создаёт (старый отзывает), рендерит страницу
  с токеном крупно один раз + предупреждение.
- POST `/token/revoke` — отзывает.
- Ссылка на страницу — в меню, где «logout» (см. шаблон base/layout,
  поиск по «logout» в templates/).
- Ссылка из d2 НЕ добавляется в шапку.

### MCP-роут `POST /mcp` (routers/mcp.py)

- Stateless JSON-RPC 2.0: запрос — объект, ответ — объект
  (`application/json`). Без SSE и `Mcp-Session-Id`.
- Auth: `Authorization: Bearer <token>`; иначе/неверный →
  401 `{"error": ...}`. Хеш → `t_api_tokens`, `revoked_at IS NULL`,
  scope содержит гранул.
- Методы: `initialize` (вернуть name/version/capabilities),
  `tools/list` (список с JSON-Schema аргументов), `tools/call`.
  Неизвестный метод → JSON-RPC error -32601; битые аргументы → -32602.
- Ошибки tools — JSON-RPC error, не 500.
- Идентичность: из токена (tg_id, username-snapshot). Права — те же
  функции, что у веба: `user_org_names(tg_id)`, `_org_visible`,
  `_d2_edit_allowed(org)` (routers/decision.py). CREATED_BY = "@username".

### Tools фазы 1

| tool                | что делает | права |
|---------------------|------------|-------|
| `d2_list_orgs`      | орги из user_org_names, видимость и edit-флаг | свой |
| `d2_list_questions` | список: NUMBER, TITLE, STATUS последнего чтения, TELEGRAM_LINK (черновик = NULL), UUID; фильтр org | _d2_edit_allowed |
| `d2_get_question`   | все чтения вопроса: BODY, STATUS, CREATED_BY, CREATED_AT, TG-ссылки | _d2_edit_allowed |
| `d2_create_draft`   | черновик: org (явно), title, body (HTML), number? (авто max+1), reading? (default). Создаёт QUESTIONS+QUESTION_DATA как веб (/d2/add), status=черновик, БЕЗ TG-поста | _d2_edit_allowed |
| `d2_update_draft`   | правка title/body/status черновика (патч существующей QUESTION_DATA-строки; смена reading — только через веб) | _d2_edit_allowed |

- publish НЕ включён (фаза 2, гранул `d2_publish` в scope уже
  поддерживается колонкой).
- Лог каждого tools/call: logger.info(mcp call user/org/tool).

### Не в скоупе (фаза 2, отдельный план)

`d2_publish` + scope `d2_publish`; перенос embed-токенов D2_PUBLIC из
Grist в t_*; перенос шаблонов; audit-таблица.

## Файлы

1. `db/sql_models.py` — класс ApiToken (рядом с BotLoginToken).
2. `routers/token.py` (новый blueprint) — GET /token, POST /token/create, POST /token/revoke; helpers: generate, hash, revoke-others, authenticate.
3. `routers/mcp.py` (новый blueprint) — POST /mcp, JSON-RPC диспетчер, реестр tools.
4. `start.py` — регистрация двух blueprint (2 строки).
5. `templates/token.html` — карточка токена.
6. Шаблон меню (где logout) — +1 пункт меню (строка).
7. `tests/fixtures/d2_stand_seed.json` — при необходимости сид.
8. `tests/routers/test_api_tokens.py` (новый) — жизненный цикл токена.
9. `tests/routers/test_mcp.py` (новый) — auth, JSON-RPC, tools.

## Приёмка

- `uv run pytest tests/routers/test_api_tokens.py tests/routers/test_mcp.py -q --no-cov` — 0 failed.
- `uv run pytest tests/ --no-cov -q` — 0 failed (регрессии).
- `ruff format --check`, `ruff check` на изменённых файлах.
- Стенд :8000 (test_mode): создать токен через /token (виден один раз),
  второй токен отзывает первый; `curl -X POST /mcp` c Bearer:
  initialize, tools/list, tools/call d2_list_orgs / d2_create_draft —
  черновик в Grist-стенде, CREATED_BY=@testuser; без Bearer — 401.
- Существующие d2-тесты зелёные (воркспейс-гейты не задеты).

## Ручной шаг владельца (прод)

Нет: таблицу создаст create_all при деплое. (Grist-таблицы не затрагиваем.)

## Статус (2026-11-04)

Готово. Фаза 1 реализована полностью, прогнано 2 круга независимого ревью
(`docs/drafts/agy_api_tokens_mcp_review.md`).

- Код: `db/sql_models.py` (ApiToken), `routers/token.py`, `routers/mcp.py`,
  `start.py`, `templates/token.html`, `templates/tabler_base.html` (пункт меню).
- Тесты: `tests/routers/test_api_tokens.py` (7), `tests/routers/test_mcp.py` (20).
- Проверки: `just check-changed` — passed; полный регресс
  `pytest tests/ -q --no-cov` — 792 passed, 1 skipped.
- Смоук (test_client, сессия itolstov): GET /token 200; POST create — токен
  показан один раз; MCP initialize → serverInfo eurmtl-me 1.0.0; tools/list →
  5 tools фазы 1; неверный Bearer → 401.
- Отклонение от плана: роуты create/revoke объединены в `POST /token`
  (action в форме) вместо отдельных `/token/create`, `/token/revoke` —
  проще CSRF/редиректы, поведение то же.
- Круг 1 ревью: P1 — импорт blueprint в start.py (прод падал на старте,
  тесты не ловили), срез readings до 1 в get_question (веб хранит одну
  строку QUESTION_DATA на чтение), username опционален в userdata,
  кеш таблиц развязан с вебом (единый loader из decision.py).
- Круг 2 ревью: P1 — не-dict params/arguments давали 500 (теперь -32602),
  KeyError при ревоке у юзера без username, битые QUESTION_ID в Grist
  роняли list_questions; P2 — reading при readings=0 ограничен 1,
  status валидируется против decision.statuses + enum в схеме tool,
  create_token принимает открытую сессию (без вложенных пулов), убран
  дублирующий flash, title strip в update, get_json(force=True) → корректный
  -32700 без Content-Type.

## Статус (2026-11-04, после 4 кругов аги-ревью) — готово

- Фаза 1 полностью реализована: /token (создание/ревок, показ один раз,
  один активный на юзера), POST /mcp (JSON-RPC 2.0, 5 tools, Bearer).
- 4 круга ревью (`docs/drafts/agy_api_tokens_mcp_review*.md`), все P1/P2
  закрыты; круг 4 — вердикт «чинить и коммитить», новых P1 нет → сходимость.
- Тесты: tests/routers/test_api_tokens.py (7) + tests/routers/test_mcp.py (33);
  полный регресс 805 passed, 1 skipped. just check-changed passed.
- Отклонение от плана: revocation выполняется POST /token с `action=
  create|revoke` вместо отдельных путей /token/create и /token/revoke.
- Фаза 2 (publish, гранул d2_publish) — вне этого плана.
