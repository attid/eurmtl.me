### Ревью незакоммиченных изменений (API-токены + MCP-эндпоинт)

Проведено детальное независимое ревью изменений в ветке:
- [sql_models.py](file:///home/itolstov/Projects/mtl/eurmtl.me/db/sql_models.py)
- [token.py](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py)
- [mcp.py](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py)
- [token.html](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html)
- [test_api_tokens.py](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_api_tokens.py)
- [test_mcp.py](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_mcp.py)
- [start.py](file:///home/itolstov/Projects/mtl/eurmtl.me/start.py), [index.py](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/index.py), [tabler_base.html](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/tabler_base.html), [app.py](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/fixtures/app.py)

---

### Находки по приоритетам

#### P1: Баги (чинить до коммита)

1. **[routers/mcp.py:440](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L440) и [routers/mcp.py:505](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L505) — Необработанный `AttributeError` и HTTP 500 при не-dict `params`**
   - **Суть**: Если клиент передает `params`, не являющийся объектом/словарём (например, `params: "string"`, `params: 123` или `params: [1, 2]`), сервер падает с HTTP 500.
   - **Почему**: На строке 440 выполняется `params = req.get("params") or {}`. Если `params` не пустой и не dict (например, строка или список), то `params.get("name")` вызывает `AttributeError: 'str' object has no attribute 'get'`. Аналогично на строке 505: `(req.get('params') or {}).get('name', '-')` падает в логгере. Поскольку вызов `_handle` в `mcp_endpoint` не обёрнут в `try/except`, исключение уходит в Quart и возвращает HTTP 500 вместо JSON-RPC ошибки `-32602` / `-32600`. То же самое касается `params.get("arguments")`: если клиент передал `arguments: "строка"`, вызовы `args.get(...)` в хендлерах инструментов выбросят `AttributeError`.
   - **Как чинить**:
     1. В `_handle`:
        ```python
        params = req.get("params")
        if not isinstance(params, dict):
            return _rpc_error(req_id, -32602, "params must be an object")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _rpc_error(req_id, -32602, "arguments must be an object")
        ```
     2. На строке 505 логгера безопасно извлекать имя:
        ```python
        tool_name = req.get("params", {}).get("name", "-") if isinstance(req.get("params"), dict) else "-"
        ```

2. **[routers/token.py:129](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L129) — `KeyError` при отзыве токена пользователем без username**
   - **Суть**: При отзыве токена пользователем, у которого в сессии `username` отсутствует или равен `None`, сервер падает с HTTP 500 (`KeyError: 'username'`).
   - **Почему**: На строке 107 при создании токена корректно используется `userdata.get("username")`, а вот на строке 129 при отзыве написано:
     `logger.info(f"API token revoked by @{userdata['username']} (tg_id={tg_id})")`. Если в `userdata` нет ключа `'username'` (пользователь без `@handle` в Telegram), происходит падение.
   - **Как чинить**:
     Использовать безопасное извлечение:
     ```python
     username = userdata.get("username") or str(tg_id)
     logger.info(f"API token revoked by @{username} (tg_id={tg_id})")
     ```

3. **[routers/mcp.py:124-125](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L124-L125) — Падение `tool_d2_list_questions` при пустых или нечисловых `QUESTION_ID` в Grist**
   - **Суть**: Если в таблице `QUESTION_DATA` в Grist есть пустая или битая строка (где `QUESTION_ID` равен `""` или не является целым числом), вызов `d2_list_questions` падает с `ValueError: invalid literal for int() with base 10: ''`.
   - **Почему**: Код делает `if r.get("QUESTION_ID") is not None: data_by_qid.setdefault(int(r["QUESTION_ID"]), []).append(r)`. В Grist пустые ячейки часто возвращаются как пустые строки `""`, что проходит проверку `is not None`, но ломает `int(...)`. В отличие от `_readings_int(row)`, где есть блок `try/except`, здесь защиты нет.
   - **Как чинить**:
     Привести к безопасному виду:
     ```python
     for r in question_data:
         qid = r.get("QUESTION_ID")
         try:
             data_by_qid.setdefault(int(qid), []).append(r)
         except (TypeError, ValueError):
             continue
     ```

---

#### P2: Стоит поправить

4. **[routers/mcp.py:220-224](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L220-L224) — Дыра валидации `reading` для организаций с `readings = 0`**
   - **Суть**: Для организаций, у которых в конфигурации `readings = 0` (одноканальные организации без чтений), агент может передать абсолютно любое числовое значение чтения (например, `reading: 999`), и валидация его пропустит.
   - **Почему**: В `_org_readings(org)` возвращается `0`. В строке 221 условие:
     `if reading < 1 or (readings_total and reading > readings_total):`.
     При `readings_total == 0` выражение `(readings_total and ...)` всегда `0` (False). Однако в `eurmtl.me` организации с `readings=0` имеют ровно одно чтение (`reading=1`, см. `templates/d2_form.html:143-144`).
   - **Как чинить**:
     ```python
     max_reading = readings_total if readings_total > 0 else 1
     if reading < 1 or reading > max_reading:
         raise ToolError(
             f"reading {reading} вне диапазона org '{org}' (max={max_reading})"
         )
     ```

5. **[routers/mcp.py:305-306](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L305-L306) и [routers/mcp.py:393-404](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L393-L404) — Отсутствие валидации и документации `status` в `d2_update_draft`**
   - **Суть**: В схеме `d2_update_draft` параметр `status` описан просто как строка (`"type": "string"`), без перечисления допустимых значений. В коде значение записывается в Grist напрямую: `fields["STATUS"] = str(args["status"])`.
   - **Почему**: AI-агент, читая `tools/list`, не знает формат статусов с эмодзи (`❗️ #active`, `☑️ #next`, `✅ #done`, `🔂 #resign`, `‼️ #control`, `🔇 #canceled`) и наверняка передаст `"active"` или `"draft"`. Запись такого статуса сломает фильтрацию и отображение в веб-интерфейсе D2.
   - **Как чинить**:
     1. В схему инструмента и описание добавить перечень допустимых статусов.
     2. В хендлере проверять:
        ```python
        from routers.decision import statuses
        if "status" in args:
            st = str(args["status"])
            if st not in statuses:
                raise ToolError(f"недопустимый статус '{st}', разрешены: {', '.join(statuses)}")
            fields["STATUS"] = st
        ```

6. **[routers/token.py:102-124](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L102-L124) — Вложенная сессия SQLAlchemy в `token_page()` при `action == "create"`**
   - **Суть**: Роут `token_page` открывает внешнюю сессию базы данных (`async with current_app.db_pool() as db_session:`), после чего внутри ветки `action == "create"` вызывает `create_token(current_app.db_pool, ...)`, которая открывает из пула *вторую* сессию, делает commit и закрывается. Затем строка 122 читает созданную запись через *первую* внешнюю сессию (`_active_token_row(db_session, tg_id)`).
   - **Почему**: Это излишне расходует соединения из пула, создаёт асимметрию с `action == "revoke"` (где используется только внешняя сессия), а в случае изоляции транзакций первая сессия потенциально может прочитать устаревший снимок данных.
   - **Как чинить**:
     Либо передавать уже открытую `db_session` в `create_token(db_session, tg_id, username, scope="d2")`, либо в `token_page` не открывать внешнюю сессию на уровне всего эндпоинта, а открывать её только там, где она реально нужна для чтения/записи.

7. **[routers/token.py:119](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L119) и [templates/tabler_base.html:247](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/tabler_base.html#L247) — Некорректная категория flash `warn` и дублирование плашки**
   - **Суть**: На строке 119 вызывается `await flash(TOKEN_TTL_MESSAGE, "warn")`. Однако в [templates/tabler_base.html:247](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/tabler_base.html#L247) логика категорий бинарна:
     `alert-{{ 'success' if category == 'good' else 'danger' }}`.
     В итоге предупреждение "Токен показывается только один раз..." отрисовывается вверху экрана как **красная ошибка** (`alert-danger`), а прямо под ней карточка [token.html:17](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html#L17) выводит точно такое же предупреждение, но в желтом блоке `alert-warning`.
   - **Как чинить**:
     Удалить вызов `await flash(TOKEN_TTL_MESSAGE, "warn")` со строки 119, так как шаблон `token.html` уже содержит красивое и исчерпывающее предупреждение в блоке `{% if new_token %}`.

8. **[routers/mcp.py:313](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L313) — Отсутствие `.strip()` для `title` в `tool_d2_update_draft`**
   - **Суть**: В `d2_create_draft` заголовок обрезается через `.strip()`. В `d2_update_draft` на строке 307 проверяется `if not str(args["title"]).strip(): raise ToolError(...)`, но в Grist отправляется исходное значение `str(args["title"])`, которое может содержать случайные пробелы по краям.
   - **Как чинить**:
     Зафиксировать `clean_title = str(args["title"]).strip()` и использовать его при обновлении.

9. **[routers/mcp.py:490](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L490) — Ложный -32600 (invalid request) при отсутствии `Content-Type: application/json`**
   - **Суть**: Метод `await request.get_json()` в Quart без `force=True` возвращает `None`, если заголовок `Content-Type` не равен строго `application/json` (например, при вызове `curl -d '{"jsonrpc": "2.0", ...}'` curl по умолчанию выставляет `application/x-www-form-urlencoded`).
   - **Почему**: Получив `None`, код на строке 494 трактует валидный JSON-RPC как `-32600 invalid request`.
   - **Как чинить**:
     Использовать `await request.get_json(force=True, silent=True)` или `json.loads(await request.get_data())` с перехватом `json.JSONDecodeError` (-32700).

---

#### P3: Вкусовщина и мелкие шероховатости

10. **[routers/mcp.py:72-98](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L72-L98) — Избыточность логики проверки прав**
    - Функция `_identity_orgs(tg_id)` уже собирает объединение организаций (подписант + секретарь). В `_d2_edit_allowed(tg_id, org)` первая проверка `if tg_id in await _org_secretary_addresses(org): return True` избыточна, так как следующая строка `return org in await _identity_orgs(tg_id)` делает ровно то же самое.
    - В `tool_d2_list_orgs` ключ `"can_edit": org.name in visible` всегда равен `True`, так как цикл идёт только по `visible`.
    - Функция-обёртка `_org_secretary_addresses` просто вызывает функцию из `routers.decision`. Можно импортировать её напрямую.

11. **[routers/mcp.py:250-251](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L250-L251) — Импорты модулей стандартной библиотеки внутри функций**
    - `import uuid as uuid_mod` и `from datetime import datetime` импортируются прямо внутри `tool_d2_create_draft`. Циклических зависимостей у них нет, их стоит вынести в начало файла.

12. **[routers/mcp.py:478](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L478) — Неиспользуемый аргумент `tool_name` в `scope_allows_from`**
    - Понятно, что это заглушка под фазу 2 (`d2_publish`), но сейчас аргумент никак не используется.

13. **[templates/token.html:34](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html#L34) — Вывод даты без указания таймзоны UTC**
    - `created_at` сохраняется как UTC. При отображении в карточке `{{ active_token.created_at.strftime('%d.%m.%Y %H:%M') }}` пользователю неочевидно, что время указано по UTC. Имеет смысл добавить постфикс `UTC`.

---

### Что упростить

1. **Убрать дублирующий flash-месседж** в [routers/token.py:119](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L119). Страница `token.html` уже выводит alert с токеном и предупреждением; flash здесь создаёт только визуальный шум и ложную красную плашку.
2. **Упростить сессии в [routers/token.py](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py)**: в функции `create_token` принимать открытую сессию `db_session` вместо `current_pool`. Это избавит от вложенных сессий и сделает транзакцию атомарной.
3. **Убрать лишнюю цепочку обёрток прав** в [routers/mcp.py:78-98](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L78-L98): свести к единой проверке `org in await _identity_orgs(tg_id)`.

---

### Чего не хватает в тестах

1. **Невалидные типы `params` и `arguments` в JSON-RPC**:
   В [tests/routers/test_mcp.py](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_mcp.py) проверен случай `"params": None`, но не проверены `"params": "not-dict"`, `"params": [1, 2]` или `{"arguments": "bad"}`.
2. **Отзыв токена пользователем без username**:
   В [tests/routers/test_api_tokens.py](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_api_tokens.py) есть тест `test_token_page_create_without_username_rejected`, но нет теста на `action="revoke"` без username.
3. **Проверка отклонения невалидного `scope` в `/mcp`**:
   Тест `test_scope_allows_granules` проверяет только чистую функцию, но ни один тест не вызывает `POST /mcp` с токеном, имеющим scope отличный от `d2` (например, `scope="other"`), чтобы проверить реакцию `-32602`.
4. **Обновление `status` в `d2_update_draft`**:
   В `test_mcp_update_draft_patches_body` проверяется обновление только `body` и `title`. Обновление статуса вообще не покрыто тестами.
5. **Грязные/пустые данные Grist**:
   Тесты работают на идеальных моках. Нет проверки поведения `d2_list_questions` при наличии в `QUESTION_DATA` пустых строк с `QUESTION_ID=""` или `QUESTION_ID=None`.
6. **Граничные значения `reading`**:
   Нет теста на создание черновика с `reading > readings_total` и для организации с `readings = 0`.

---

### Вердикт

**Чинить и коммитить.** (Находки P1 и P2 имеют точечный характер, их исправление сделает код надёжным и предотвратит падения в продакшене).
