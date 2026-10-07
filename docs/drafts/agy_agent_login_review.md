Запустил тесты `tests/routers/test_agent_login.py` для проверки текущего состояния. Ожидаю завершения.
## Ревью фичи Agent Login (bocaccio)

> **Статус рабочей копии:**  
> В коммитах `e735029` и `72e6962` зафиксирована начальная реализация (9 тестов). В рабочей директории обнаружен незакоммиченный diff (еще 8 тестов и ряд точечных правок). Ниже приведено полное ревью коммита `e735029` с обязательным указанием того, что уже подготовлено в незакоммиченном diff, а что еще требует внимания.

---

### Находки по приоритетам

#### P1 (Критические баги — чинить до коммита)

1. **Краш приложения при старте из-за дублирования Blueprint**
   - **Файл:строка:** [routers/agent_login.py:20](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L20), [start.py:47](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/start.py#L47) *(в `e735029`)*
   - **Суть:** В коммите `e735029` модуль `routers/agent_login.py` импортировал `blueprint` из `routers.index` (`from .index import blueprint`). В `start.py` выполнялось:
     ```python
     app.register_blueprint(routers.index.blueprint)
     app.register_blueprint(routers.agent_login.blueprint)
     ```
   - **Почему:** В Quart попытка дважды зарегистрировать один и тот же Blueprint с именем `"index"` приводит к фатальной ошибке при старте: `ValueError: The name 'index' is already registered for this blueprint.` Приложение просто не запускалось. Юнит-тесты в `e735029` этого не заметили, так как в [tests/fixtures/app.py](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/tests/fixtures/app.py) `agent_login.blueprint` вообще не регистрировался.
   - **Как чинить:** Выделить для агента собственный Blueprint: `blueprint = Blueprint("agent_login", __name__)`, зарегистрировать его в [start.py](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/start.py) и [tests/fixtures/app.py](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/tests/fixtures/app.py#L63). *(Уже сделано в unstaged diff, необходимо закоммитить)*.

2. **Пропуск валидации веса подписанта (`weight == 0`)**
   - **Файл:строка:** [routers/agent_login.py:108-111](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L108-L111) *(в `e735029`)*
   - **Суть:** Поиск подписанта выполнялся как `next((s for s in signers if s.get("key") == address), None)`.
   - **Почему:** В протоколе Stellar отзыв прав подписанта или перевод счета фонда в чистый мультисиг осуществляется установкой `weight = 0`. В списке `signers` на Horizon такие ключи могут присутствовать (в частности, сам мастер-ключ счета). В версии `e735029` ключ с `weight: 0` успешно проходил авторизацию, что прямо противоречит согласованному ТЗ (*«weight > 0 on Horizon»*).
   - **Как чинить:** Добавить условие на вес: `signer = next((s for s in signers if s.get("key") == address and s.get("weight", 0) > 0), None)`. *(Уже сделано в unstaged diff)*.

3. **Сбой 500 на защищенных роутах при отсутствии `telegram_id` в Grist**
   - **Файл:строка:** [routers/agent_login.py:113-125](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L113-L125) *(в `e735029`)*
   - **Суть:** Проверялось только `if user is None: return _agent_error("no_grist_user", 403)`.
   - **Почему:** Если у агента/бота в таблице `EURMTL_users` поле `telegram_id` не заполнено (`None`), то в сессию записывалось `session["user_id"] = "None"`. При любом последующем запросе (например, в `/decision`) функция [`check_user_weight()`](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/services/stellar_client.py#L252) выполняет `int(user_id)` и падает с `ValueError: invalid literal for int() with base 10: 'None'` (HTTP 500). Если же `telegram_id == 0`, то `check_user_weight()` ошибочно сопоставлял его с первым попавшимся неподписантом с `telegram_id == 0`.
   - **Как чинить:** Проверять: `if user is None or not user.telegram_id: return _agent_error("no_grist_user", 403)`. *(Уже сделано в unstaged diff)*.

4. **Падение 500 при некорректном теле запроса (не-JSON, списки, не-строковые поля)**
   - **Файл:строка:** [routers/agent_login.py:76-80, 52](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L76-L80) *(в `e735029`)*
   - **Суть:** Нестрогая валидация входящих типов данных.
   - **Почему:**
     - Если клиент отправлял JSON-массив `[1, 2, 3]`, вызов `data.get(...)` падал с `AttributeError` -> 500.
     - Если поле `signature` передавалось как число (`{"signature": 123}`), вызов `base64.b64decode(123)` выбрасывал `TypeError`, который не ловился в `except (binascii.Error, ValueError)` -> 500.
   - **Как чинить:** Добавить проверку `isinstance(data, dict)` и `isinstance(..., str)` для всех трех полей, а в `_decode_signature` перехватывать также `TypeError`. *(Уже сделано в unstaged diff)*.

5. **Фиксация сессии (Session Fixation) и отсутствие явной очистки**
   - **Файл:строка:** [routers/agent_login.py:117-124](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L117-L124) *(в `e735029`)*
   - **Суть:** Сессия не сбрасывалась перед установкой данных авторизации.
   - **Почему:** Если агент отправлял запрос с уже существующим cookie (например, от анонимной сессии или предыдущего пользователя с `return_to`, OIDC-параметрами), ключи не сбрасывались. Кроме того, не проставлялся `session.permanent = True`, из-за чего cookie мог выпускаться как сессионный без TTL 7 дней.
   - **Как чинить:** Вызывать `session.clear()` и `session.permanent = True` перед записью `userdata`. *(Уже сделано в unstaged diff)*.

---

#### P2 (Стоит поправить)

1. **Обработка пустого `username` в Grist**
   - **Файл:строка:** [routers/agent_login.py:121](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L121)
   - **Суть:** `username = (user.username or "").lstrip("@")`.
   - **Почему:** Если в Grist у бота нет username (пусто или `None`), в сессию запишется `username = ""`. Далее в [routers/decision.py:97](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/decision.py#L97) код конкатенирует `username = "@" + session["userdata"]["username"]`, в результате в посты Telegram и таблицу решений автор запишется как `"@"`.
   - **Как чинить:** Добавить безопасный fallback, например:
     ```python
     username = (user.username or "").lstrip("@") or f"bot_{address[:8]}"
     ```

2. **Чувствительность к пробелам и переводам строк (`\n`) в `signature` и `address`**
   - **Файл:строка:** [routers/agent_login.py:48-63, 79-81](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L48-L63)
   - **Суть:** Отсутствует `.strip()` на входных строках.
   - **Почему:** Машинные агенты и скрипты часто считывают подписи или ключи из вывода CLI/файлов, где присутствует завершающий перевод строки (`\n`) или пробелы. Из-за `validate=True` в `base64.b64decode` наличие пробела/`\n` вызывает `binascii.Error`, и запрос отклоняется с 400 `bad_signature`.
   - **Как чинить:** Делать `signature = signature.strip()`, `address = address.strip()`, `nonce = nonce.strip()`.

3. **Синхронизация плана задачи**
   - **Файл:строка:** [docs/exec-plans/active/agent-bot-login.md:13](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/docs/exec-plans/active/agent-bot-login.md#L13)
   - **Суть:** В плане зафиксировано: `blueprint реюзнут из routers/index.py`.
   - **Почему:** Это не соответствует финальному решению (выделен отдельный Blueprint `agent_login`). Документация вводит в заблуждение последующих разработчиков.
   - **Как чинить:** Заменить формулировку на «выделен собственный blueprint `agent_login`, зарегистрирован в `start.py`».

4. **Пример вызова в документации для агентов**
   - **Файл:строка:** [templates/llm.txt:54](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/templates/llm.txt#L54)
   - **Суть:** В коммите `e735029` пример содержал `POST /login/agent with base64(signature)`. В стандартной библиотеке Python модуль `base64` не вызывается как функция.
   - **Как чинить:** В unstaged diff уже исправлено на `base64.b64encode(signature).decode()`. Стоит также явно упомянуть hex: `signature.hex()`.

---

#### P3 (Вкусовщина и архитектурные заметки)

1. **Неэффективный порядок декодирования подписи**
   - **Файл:строка:** [routers/agent_login.py:48-63](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L48-L63)
   - **Суть:** Hex-подпись (128 символов hex) всегда является валидным Base64-алфавитом. `b64decode` сначала успешно декодирует 128 символов в 96 байт, отбрасывает их по `len == 64`, и только затем переходит к `bytes.fromhex`.
   - **Как чинить:** Проще и быстрее проверять длину строки:
     ```python
     sig = signature.strip()
     if len(sig) == 128:
         try: return bytes.fromhex(sig)
         except ValueError: pass
     elif len(sig) in (86, 88):
         try: return base64.b64decode(sig, validate=True)
         except Exception: pass
     ```

2. **Ограничение multi-worker при in-process хранилище nonce**
   - **Файл:строка:** [routers/agent_login.py:28](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L28)
   - **Суть:** `_agent_nonce_store` хранится в памяти одного процесса. Сейчас сервер запускается в один процесс через `uvicorn.run(...)`, поэтому всё работает. При потенциальном масштабировании на несколько воркеров uvicorn нонсы между воркерами не синхронизируются (аналогично `remote_sep07_auth.py`). Рекомендуется оставить комментарий в коде о single-process допущении.

3. **Отсутствие поддержки URL-safe Base64**
   - **Файл:строка:** [routers/agent_login.py:52](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/routers/agent_login.py#L52)
   - **Суть:** Некоторые криптобиблиотеки отдают base64 в url-safe формате (`-` и `_`). `b64decode(..., validate=True)` вернет ошибку. Можно использовать `urlsafe_b64decode`.

---

### Что упростить

1. **Убрать вызов очистки хранилища из POST-эндпоинта** *(сделано в unstaged)*:  
   В `e735029` при каждом POST выполнялся полный проход по хранилищу `_agent_nonce_cleanup()`. Это избыточно: операция `_agent_nonce_store.pop(nonce, None)` атомарна и выполняется за $O(1)$. Достаточно делать cleanup только на `GET /login/agent`.
2. **Детектирование формата подписи по длине**:  
   Вместо слепого перебора `b64decode` $\to$ `fromhex` с обработкой исключений, явная проверка длины (128 vs 88) делает код более читаемым и быстрым.

---

### Чего не хватает в тестах

В коммите `e735029` было 9 тестов, в unstaged diff добавлено еще 8 (всего 17). Однако даже с учетом новых тестов остаются незакрытые зоны:

1. **Сквозной тест авторизованного запроса на защищенный роут:**  
   Ни один тест не делает последующий запрос с полученной cookie на реальный метод приложения (например, `POST /decision`), использующий [`check_user_weight()`](file:///home/itolstov/orca/workspaces/eurmtl.me/bocaccio/services/stellar_client.py#L243). Именно поэтому P1-баг с `telegram_id == None` не был пойман тестами.
2. **Тест на не-JSON тело запроса:**  
   Запрос с `Content-Type: text/plain` или поврежденным JSON (`client.post("/login/agent", data="not json", content_type="text/plain")`).
3. **Проверка CORS-заголовков:**  
   Используется `cors_jsonify`, но нет проверки наличия заголовков `Access-Control-Allow-Origin: *` в ответах GET и POST.
4. **Юникод и спецсимволы в полях:**  
   Тесты на поведение при передаче подписи с кириллицей, эмодзи (`👍`) или адреса с zero-width пробелом (`GACK\u200b...`).
5. **Тест на вытеснение nonces при переполнении (FIFO eviction):**  
   Проверка, что при превышении `AGENT_NONCE_MAX_STORE` старые неиспользованные нонсы удаляются, а свежие остаются валидными.
6. **Гонка при параллельных запросах с одним nonce:**  
   Проверка, что при двух одновременных POST с одинаковым nonce ровно один запрос успешен, а второй стабильно получает 400 `nonce_expired`.

---

### Вердикт

**Чинить и коммитить** (закоммитить подготовленные в рабочей копии исправления для P1, учесть замечания P2).
