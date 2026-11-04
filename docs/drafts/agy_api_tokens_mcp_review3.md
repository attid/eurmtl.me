### Ревью незакоммиченных изменений (API-токены + MCP-эндпоинт)

Проведено детальное независимое ревью диффа и новых файлов:
- [`db/sql_models.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/db/sql_models.py)
- [`routers/token.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py)
- [`routers/mcp.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py)
- [`templates/token.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html)
- [`tests/routers/test_api_tokens.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_api_tokens.py)
- [`tests/routers/test_mcp.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_mcp.py)
- [`start.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/start.py), [`routers/index.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/index.py), [`templates/tabler_base.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/tabler_base.html), [`templates/llm.txt`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/llm.txt), [`tests/fixtures/app.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/fixtures/app.py)

---

### Находки по приоритетам

#### P1: Баги (чинить до коммита)

1. **[`routers/mcp.py:300`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L300) и [`routers/mcp.py:310`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L310) — Запись строкового литерала `"None"` в Grist при передаче `null` в опциональных полях `title`, `body` в `d2_update_draft`**
   - **Суть**: Если AI-агент вызывает `d2_update_draft` и передает `null` для неизменяемых полей (например, `{"uuid": "...", "body": "<p>новое тело</p>", "title": null}`), заголовок вопроса в Grist перезаписывается строкой `"None"`. Если передать `"body": null`, тело вопроса заменяется на `"None"`. При `"status": null` вызов аварийно завершается, так как строка `"None"` не входит в список допустимых статусов.
   - **Почему**: Проверки `if "body" in args:` и `if "title" in args:` срабатывают при наличии ключа со значением `None`. В Python `str(None)` дает `"None"`, а `clean_title = str(args["title"]).strip() if "title" in args else None` становится непустой строкой `"None"`, которая отправляется в `MTLGrist.QUESTIONS`.
   - **Как чинить**: Проверять не только наличие ключа, но и то, что значение не `None`:
     ```python
     if "body" in args and args["body"] is not None:
         fields["BODY"] = str(args["body"])
     if "status" in args and args["status"] is not None:
         st = str(args["status"])
         if st not in statuses:
             raise ToolError(
                 f"недопустимый статус '{st}', разрешены: {', '.join(statuses)}"
             )
         fields["STATUS"] = st
     clean_title = (
         str(args["title"]).strip()
         if ("title" in args and args["title"] is not None)
         else None
     )
     ```

2. **[`routers/mcp.py:240-244`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L240-L244) — Необработанный `StopIteration` и пустое сообщение `error: ` в `tool_d2_create_draft`**
   - **Суть**: Строка `question_id = next(q["id"] for q in questions if q.get("NUMBER") == number and _question_org(q) == org)` выбрасывает `StopIteration`, если Grist вернул `NUMBER` как строку (например `"3"`, а переменная `number` — число `3`), либо если только что созданная запись ещё не попала в кеш. Исключение перехватывается общим блоком `except Exception as e:`, но так как `str(StopIteration()) == ""`, клиент получает бесполезный ответ: `{"isError": true, "content": [{"type": "text", "text": "error: "}]}`.
   - **Почему**: `next()` вызывается без значения по умолчанию (в отличие от соседних функций, где используется `next(..., None)`). Кроме того, в [`routers/decision.py:1151`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L1151) сравнение номеров выполняется безопасно через строку: `str(q.get("NUMBER")) == str(question_number)`.
   - **Как чинить**:
     ```python
     question = next(
         (
             q
             for q in questions
             if str(q.get("NUMBER")) == str(number) and _question_org(q) == org
         ),
         None,
     )
     if question is None:
         raise ToolError(f"не удалось найти созданный вопрос №{number} в org '{org}'")
     question_id = question["id"]
     ```

3. **[`routers/mcp.py:141`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L141) — Сбой `tool_d2_list_questions` при сортировке вопросов со смешанными типами `NUMBER`**
   - **Суть**: `result.sort(key=lambda x: (x["number"] is None, x["number"]))` завершается исключением `TypeError: '<' not supported between instances of 'str' and 'int'`, если в Grist у части вопросов в организации колонка `NUMBER` возвращается числом, а у части — строкой. Весь вызов инструмента падает с ошибкой.
   - **Почему**: В Grist ячейки могут содержать разнородные типы. В Python 3 сравнение `str` и `int` при сортировке кортежей вызывает ошибку.
   - **Как чинить**:
     Приводить значение к числу в ключе сортировки:
     ```python
     def _number_sort_key(val):
         if val is None:
             return (1, 0)
         try:
             return (0, int(val))
         except (TypeError, ValueError):
             return (0, 0)

     result.sort(key=lambda x: _number_sort_key(x["number"]))
     ```

---

#### P2: Стоит поправить

4. **[`templates/token.html:3`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html#L3) — Неверное имя блока заголовка `{% block title %}` вместо `{% block page_title %}`**
   - **Суть**: На странице `/token` в заголовке шапки выводится заглушка `"Page Title"` вместо `"API token"`.
   - **Почему**: Базовый шаблон [`templates/tabler_base.html:237`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/tabler_base.html#L237) объявляет блок `{% block page_title %}Page Title{% endblock %}`. Блока `{% block title %}` в базе нет. Все шаблоны репозитория используют `page_title`.
   - **Как чинить**: Заменить строку 3 на `{% block page_title %}API token{% endblock %}`.

5. **[`templates/token.html:6-9`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html#L6-L9) — Нарушение верстки: вложенный `.page.page-center` и двойной `.card` внутри базового `.card-body`**
   - **Суть**: `token.html` оформлен как автономная страница входа (`.page.page-center > .container-tight > .card > .card-body`). Однако `tabler_base.html:263-265` уже оборачивает `{% block content %}` в `.card > .card-body`. В результате получается двойная рамка карточки, а класс `.page-center` (`min-height: 100vh`) ломает вертикальные отступы внутри страницы.
   - **Почему**: Разметка скопирована со standalone-страниц логина.
   - **Как чинить**: Убрать обертки `.page`, `.page-center`, `.container-tight`, внутренний `.card` и `.card-body`, оставив содержимое напрямую внутри `{% block content %}` (как сделано в [`templates/tabler_bot_login.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/tabler_bot_login.html)).

6. **[`routers/mcp.py:146`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L146) и [`routers/mcp.py:278`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L278) — Поиск по пустой строке UUID при отсутствии параметра**
   - **Суть**: Если `uuid` не передан или передан пустым (`""`), код выполняет поиск `r.get("UUID") == ""` по всей таблице `QUESTION_DATA`. Если в Grist присутствует пустая строка, она будет ошибочно выбрана.
   - **Почему**: `uuid_ = str(args.get("uuid") or "")` не проверяет непустоту строки перед поиском.
   - **Как чинить**:
     ```python
     uuid_ = str(args.get("uuid") or "").strip()
     if not uuid_:
         raise ToolError("поле 'uuid' обязательно")
     ```

7. **[`routers/mcp.py:210`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L210) — Скрытая коэрция `reading: 0` в `1`**
   - **Суть**: Вызов `d2_create_draft` с аргументом `reading: 0` превращается в чтение `1` из-за выражения `args.get("reading") or 1` (поскольку `0 or 1 == 1`). При этом строковое значение `"0"` валидацию не проходит и отбрасывается.
   - **Почему**: Использование оператора `or` на числовом поле, где `0` является falsy-значением.
   - **Как чинить**:
     ```python
     raw_reading = args.get("reading")
     try:
         reading = 1 if raw_reading is None else int(raw_reading)
     except (TypeError, ValueError):
         raise ToolError(
             f"'reading' должен быть целым числом, получено: {raw_reading!r}"
         )
     ```

8. **[`routers/mcp.py:196-205`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L196-L205) — Отсутствие проверки на неположительный номер вопроса (`number < 1`)**
   - **Суть**: Агент может передать `{"number": -1}` или `{"number": 0}`, и валидация это пропустит. В Grist будет создана запись с отрицательным номером вопроса.
   - **Почему**: Проверяется только уникальность занятых номеров, но нет проверки нижней границы.
   - **Как чинить**: Добавить проверку `if number < 1: raise ToolError(f"номер вопроса должен быть >= 1, получено: {number}")`.

9. **[`routers/token.py:101`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L101) — Потенциальный `KeyError: 'id'` при неполных данных сессии**
   - **Суть**: `tg_id = int(userdata["id"])` напрямую обращается по ключу `"id"`. Если сессия повреждена, возникнет необработанное исключение и HTTP 500 вместо редиректа на `/login`.
   - **Почему**: В [`routers/decision.py:151-158`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L151-L158) извлечение защищено через `get` и блок `try/except`.
   - **Как чинить**:
     ```python
     user_id = userdata.get("id")
     try:
         tg_id = int(user_id)
     except (TypeError, ValueError):
         return redirect("/login")
     ```

10. **[`routers/token.py:46-60`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L46-L60) — Несоответствие docstring и реализации `create_token` + асимметрия коммитов**
    - **Суть**: В докстринге `create_token` указано: `Сессию открывает вызывающий: commit на нём`, но на строке 59 вызывается `await db_session.commit()`. При этом парная функция `revoke_active_tokens` коммит не делает.
    - **Почему**: Артефакт рефакторинга сессий круга 2.
    - **Как чинить**: Либо убрать `commit` из `create_token` и делать его в `token_page` (как при `action == "revoke"`), либо синхронизировать документацию функции.

---

#### P3: Вкусовщина и мелкие шероховатости

11. **[`routers/token.py:21-24`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py#L21-L24) — Мертвый код (`TOKEN_TTL_MESSAGE`)**
    - Константа `TOKEN_TTL_MESSAGE` осталась после удаления дублирующего flash-сообщения и нигде в коде не используется. Стоит удалить.

12. **[`routers/mcp.py:494-496`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L494-L496) — Неиспользуемый аргумент `tool_name` в `scope_allows_from`**
    - Параметр `tool_name` никак не используется в теле функции. Можно убрать параметр или проверять `scope_allows(scope, "d2")` прямо в диспетчере.

13. **[`routers/mcp.py:191`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L191), [`routers/mcp.py:246-247`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L246-L247), [`routers/mcp.py:279`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L279) — Локальные импорты внутри функций**
    - `import uuid as uuid_mod`, `from datetime import datetime` и `from other.grist_tools import grist_manager, MTLGrist` импортируются внутри хендлеров инструментов. Циклических зависимостей у них нет, их стоит вынести в начало файла.

14. **[`routers/mcp.py:322, 324`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L322-L324) — Двойная инвалидация кеша**
    - Если в `d2_update_draft` обновляются и поля чтения (`fields`), и заголовок (`clean_title`), `_invalidate_cache()` вызывается дважды подряд. Достаточно вызвать один раз в конце.

15. **[`routers/mcp.py:155-157`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L155-L157) и [`routers/mcp.py:294-296`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L294-L296) — Раскрытие имени организации в сообщении об ошибке**
    - При запросе чужого вопроса по UUID возвращается `ToolError("org '<ORG>' недоступна")`, что подтверждает валидность UUID и раскрывает организацию. В [`routers/decision.py:565`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L565) действует принцип «существование не палить» (`Decision not exist`). Безопаснее возвращать `вопрос с uuid '...' не найден`.

---

### Что упростить

1. **Проверка прав в [`routers/mcp.py:87-92`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py#L87-L92)**:
   Сейчас `_d2_edit_allowed(tg_id, org)` вызывает `_identity_orgs(tg_id)`, который опрашивает секретарство во всех организациях конфига. Для точечной проверки организации достаточно:
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
   Это полностью соответствует логике [`routers/decision.py:134-146`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L134-L146) и исключает лишние сетевые запросы по другим организациям.
2. **Убрать обертку `scope_allows_from`**:
   Функция-однострочник с неиспользуемым параметром; прямой вызов `scope_allows(scope, "d2")` прозрачнее.
3. **Упростить верстку [`templates/token.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/token.html)**:
   Удалить лишние контейнеры `.page`, `.page-center`, `.card`, `.card-body` — базовый шаблон уже предоставляет каркас карточки.
4. **Удалить неиспользуемую константу `TOKEN_TTL_MESSAGE`** в [`routers/token.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/token.py).
5. **Вынести повторные импорты в начало файла** в [`routers/mcp.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/mcp.py).

---

### Чего не хватает в тестах

1. **Передача `null` в опциональные аргументы `d2_update_draft`**:
   Проверить, что вызов с `{"uuid": "...", "title": None, "body": "<p>новое</p>"}` не записывает строку `"None"` в заголовок в Grist.
2. **Успешное обновление статуса в `d2_update_draft`**:
   Сейчас протестировано только отклонение невалидного статуса (`test_mcp_update_draft_bad_status_rejected`). Нет теста на успешную передачу валидного статуса (например `☑️ #next`) в patch-запрос Grist.
3. **Граничные значения `number` и `reading` в `d2_create_draft`**:
   - `{"number": 0}` и `{"number": -1}` (проверка отклонения).
   - `{"reading": 0}` (проверка отклонения, а не превращения в 1).
   - `{"reading": 99}` (проверка отклонения превышения `max_reading`).
4. **Пустой или отсутствующий `uuid`**:
   Проверить реакцию `d2_get_question` и `d2_update_draft` на `{"uuid": ""}` и `{"uuid": "non-existent"}`.
5. **Создание и обновление черновика в чужой организации**:
   Тесты с `plain_token` на вызовы `d2_create_draft` и `d2_update_draft` с организацией `PFM` (проверка изоляции прав на запись).
6. **Вызов `POST /mcp` с токеном с неподходящим scope**:
   Вызов с токеном со `scope="other"` — проверка ответа с кодом `-32602`.
7. **Смешанные типы `NUMBER` в `d2_list_questions`**:
   Тест с фикстурой, где у одного вопроса `NUMBER` — `1` (int), а у другого — `"2"` (str), для предотвращения регрессий сортировки.

---

### Вердикт

**Чинить и коммитить.**
