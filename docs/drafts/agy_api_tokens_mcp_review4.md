### Ревью незакоммиченных изменений (API-токены + MCP-эндпоинт)

Проведено детальное независимое ревью текущих изменений:
- [`db/sql_models.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/db/sql_models.py)
- [`routers/token.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py)
- [`routers/mcp.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py)
- [`templates/token.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html)
- [`start.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/start.py)
- [`routers/index.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/index.py)
- [`templates/tabler_base.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/tabler_base.html)
- [`templates/llm.txt`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/llm.txt)
- [`tests/routers/test_api_tokens.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_api_tokens.py)
- [`tests/routers/test_mcp.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_mcp.py)

---

### Находки по приоритетам

#### P1: Баги (чинить до коммита)

1. **[`routers/mcp.py:216-219`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L216-L219) — Пропуск дубликата номера вопроса при строковом типе `NUMBER` в Grist и перезапись чужого черновика**
   - **Суть**: В `tool_d2_create_draft` проверка занятости переданного номера выполняется как:
     ```python
     if any(q.get("NUMBER") == number and _question_org(q) == org for q in questions):
         raise ToolError(f"номер {number} в org '{org}' уже занят")
     ```
     Если в Grist значение колонки `NUMBER` возвращается строкой (например, `"1"`), а переменная `number` — число `1`, сравнение `"1" == 1` ложно. Дубликат номера **не отсекается**.
     Вследствие этого в `MTLGrist.QUESTIONS` создается строка-дубликат с тем же номером. Затем на строке 259 поиск созданной записи `question = next((q for q in questions if str(q.get("NUMBER")) == str(number)...), None)` находит **первый (старый)** вопрос с этим номером и привязывает новый `QUESTION_DATA`-черновик к старому вопросу вместо нового!
   - **Почему**: На строке 259 автор уже привел сравнение к строкам `str(q.get("NUMBER")) == str(number)`, и в [`routers/decision.py:1105`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L1105) веб-код также делает `str(q.get("NUMBER")) == str(question_number)`. Однако на строке 217 осталось прямое сравнение без нормализации типов.
   - **Как чинить**: Привести сравнение к строкам:
     ```python
     if any(
         str(q.get("NUMBER")) == str(number) and _question_org(q) == org
         for q in questions
     ):
         raise ToolError(f"номер {number} в org '{org}' уже занят")
     ```

2. **[`routers/mcp.py:492-494`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L492-L494) — Ложная валидация и обход проверки типа `arguments`, если переданы `[]`, `""` или `false`**
   - **Суть**: Строка `args = params.get("arguments") or {}` выполняется **до** проверки `if not isinstance(args, dict):`. Если клиент отправляет `"arguments": []` (пустой JSON-массив) или любое falsy-значение не-типа `dict` (например `""` или `false`), оператор `or` неявно подменяет его на `{}`. В результате вызов инструмента выполняется успешно с пустыми аргументами вместо возврата стандартной ошибки JSON-RPC `-32602` (`arguments must be an object`).
   - **Почему**: Дефолтный fallback через `or` для параметров запроса маскирует некорректный тип входных данных.
   - **Как чинить**: Разделять дефолтное отсутствие ключа (`None`) и валидацию типа:
     ```python
     raw_args = params.get("arguments")
     if raw_args is None:
         args = {}
     elif not isinstance(raw_args, dict):
         return _rpc_error(req_id, -32602, "arguments must be an object")
     else:
         args = raw_args
     ```

---

#### P2: Стоит поправить

3. **[`routers/mcp.py:126-129`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L126-L129) — Потеря чтений с `READING == 0` в `tool_d2_list_questions` из-за truthiness-проверки**
   - **Суть**: В `tool_d2_list_questions` генератор отбирает чтения условием `if _readings_int(r)`. Если у организации чтение равно `0` (в [`other/orgs_config.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/other/orgs_config.py#L40) у USDMM `readings: 0`), функция `_readings_int` возвращает `0`. В Python `bool(0) is False`, поэтому чтение с номером `0` полностью отфильтровывается. У такого вопроса `readings` оказывается пустым `[]`, `last` — `{}` и `uuid` возвращается пустой строкой `""`.
   - **Почему**: `0` является валидным числом, но в условии `if _readings_int(r)` трактуется как ложь.
   - **Как чинить**: Проверять явное отличие от `None`:
     ```python
     readings = sorted(
         (r for r in data_by_qid.get(q["id"], []) if _readings_int(r) is not None),
         key=_readings_int,
     )
     ```

4. **[`routers/mcp.py:162-164`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L162-L164), [`routers/mcp.py:172`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L172) и [`routers/mcp.py:312-315`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L312-L315) — Сбой сопоставления `QUESTION_ID` при строковом представлении в Grist**
   - **Суть**: В `tool_d2_get_question` и `tool_d2_update_draft` вопрос ищется через `q.get("id") == row.get("QUESTION_ID")`. Если Grist вернул `QUESTION_ID` строкой (например, `"11"`), а в `QUESTIONS` колонка `id` является числом `11`, сравнение дает `False`, и возвращается `ToolError` («вопрос/чтение с uuid не найден(о)»). В то же время в `tool_d2_list_questions:118` автор уже учел это и сделал `int(r["QUESTION_ID"])`.
   - **Почему**: Разнородная типизация в ячейках Grist.
   - **Как чинить**: Сравнивать строковые представления:
     ```python
     question = next(
         (q for q in questions if str(q.get("id")) == str(row.get("QUESTION_ID"))),
         None,
     )
     ```
     И на строке 172 для выборки всех чтений:
     ```python
     rows = [r for r in question_data if str(r.get("QUESTION_ID")) == str(qid)]
     ```

5. **[`routers/token.py:65-72`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L65-L72) — Выборка отозванных токенов из БД в `authenticate_bearer` вместо фильтрации в SQL**
   - **Суть**: Запрос к БД ищет токен только по `token_hash`, а проверка отзыва `if token.revoked_at is not None` выполняется в Python.
   - **Почему**: Неидиоматично для SQLAlchemy и заставляет приложение вычитывать отозванные сущности в память.
   - **Как чинить**: Добавить условие `ApiToken.revoked_at.is_(None)` прямо в SQL `filter`:
     ```python
     async with current_app.db_pool() as db_session:
         result = await db_session.execute(
             select(ApiToken).filter(
                 ApiToken.token_hash == hash_token(raw),
                 ApiToken.revoked_at.is_(None),
             )
         )
         token = result.scalars().first()
     return token
     ```

---

#### P3: Вкусовщина и мелкие шероховатости

6. **[`routers/token.py:31-39`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L31-L39) — Итерация по ORM-моделям для отзыва вместо одного SQL `update`**
   - `revoke_active_tokens` делает `select`, загружает список объектов и в цикле выставляет `token.revoked_at = now`. Единый запрос `update(ApiToken).where(ApiToken.tg_id == tg_id, ApiToken.revoked_at.is_(None)).values(revoked_at=now)` атомарен на уровне БД и выполняется за один roundtrip.

7. **[`routers/mcp.py:87-92`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L87-L92) — Избыточный опрос всех организаций в `_d2_edit_allowed`**
   - При проверке конкретной организации (`_d2_edit_allowed(tg_id, org)`) вызывается `_identity_orgs(tg_id)`, который опрашивает всех секретарей для всех организаций конфига. Проще и быстрее проверять целевую организацию напрямую (как в [`routers/decision.py:134-146`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L134-L146)):
     ```python
     async def _d2_edit_allowed(tg_id: int, org: str) -> bool:
         if not org:
             return False
         from routers.decision import _org_secretary_addresses
         if tg_id in await _org_secretary_addresses(org):
             return True
         from other.grist_tools import user_org_names
         return org in set(await user_org_names(tg_id))
     ```

8. **[`routers/mcp.py:267-268`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L267-L268) — Локальные импорты стандартных библиотек (`uuid`, `datetime`) внутри хендлера**
   - Внутри `tool_d2_create_draft` присутствуют `import uuid as uuid_mod` и `from datetime import datetime`. Циклических зависимостей нет, их стоит вынести на уровень модуля.

9. **[`routers/mcp.py:358`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L358) — Поле `"title"` попадает в `updated`, даже если заголовок не менялся**
   - Если передан `title`, совпадающий с текущим, в Grist он не отправляется, но в результирующем списке `"updated"` поле `"title"` возвращается. Логичнее включать в `updated` только те поля, которые реально отправлялись в PATCH.

10. **[`docs/exec-plans/active/2026-11-04-api-tokens-mcp.md:93`](file:///home/itolstov/Projects/mtl/eurmtl.me/docs/exec-plans/active/2026-11-04-api-tokens-mcp.md#L93) — Несинхронизированность плана: упоминание `reading` в `d2_update_draft`**
    - В таблице плана указано: `d2_update_draft | правка title/body/reading черновика...`, однако в коде, JSON-схеме и в [`templates/llm.txt`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/llm.txt#L59) редактирование `reading` через MCP не предусмотрено (только `title`, `body`, `status`). Стоит актуализировать строку в плане.

---

### Что упростить

1. **SQL-выражение для отзыва токенов**: Заменить цикл выборки и мутации объектов в [`routers/token.py:31-39`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L31-L39) на один `update(ApiToken)...`.
2. **Точечная проверка прав в `_d2_edit_allowed`**: Проверять права для переданного `org` напрямую, без вызова `_identity_orgs` (оставить `_identity_orgs` только для инструмента `d2_list_orgs`).
3. **Фильтрация активного токена в SQL**: В `authenticate_bearer` перенести проверку `revoked_at IS NULL` в SQL-запрос.
4. **Вынести импорты**: Перенести импорты `uuid`, `datetime`, `grist_manager` и `MTLGrist` в начало файла [`routers/mcp.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py).

---

### Чего не хватает в тестах

1. **Тест на дубликат номера при строковом `NUMBER` в Grist**: Проверить, что при наличии вопроса с `NUMBER: "1"` попытка создать черновик с `number: 1` отклоняется с ошибкой `"номер 1 в org 'PFM' уже занят"`.
2. **Тест на обработку чтения с `READING == 0`**: Проверить, что `tool_d2_list_questions` корректно возвращает вопрос и его UUID, если в данных чтение имеет номер `0`.
3. **Тест на строковый `QUESTION_ID` в `QUESTION_DATA`**: Убедиться, что `d2_get_question` и `d2_update_draft` находят вопрос, если `r["QUESTION_ID"] = "1"` (строка), а `q["id"] = 1` (число).
4. **Тест на успешное обновление поля `status` в `d2_update_draft`**: Сейчас есть тесты на отклонение невалидного статуса и игнорирование `null`, но нет проверки применения валидного статуса (например, `"status": "☑️ #next"`).
5. **Тест на вызов `d2_update_draft` с несуществующим `uuid`**: Проверка возврата `ToolError("чтение с uuid '...' не найдено")`.
6. **Тест на вызов `d2_update_draft` для вопроса чужой организации**: Проверить, что токен без прав на целевую организацию получает «не найдено» (без раскрытия существования вопроса).
7. **Тест на передачу `"arguments": []` (пустой массив) в `tools/call`**: Проверить возврат JSON-RPC ошибки `-32602` (`arguments must be an object`).
8. **Тест на отправку пустого тела запроса (`b""`) на `POST /mcp`**: Проверить возврат ошибки `-32700` (`parse error`).

---

### Вердикт

**Чинить и коммитить.**
