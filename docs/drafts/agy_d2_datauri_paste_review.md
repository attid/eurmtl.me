root agent idle; waiting up to 30m0s for 1 background task(s)
Запустил выполнение тестов через `just test`, ожидаю завершения.
Ожидаю завершения тестов.
# Ревью незакоммиченных изменений (d2 data-URI paste)

Проведено независимое ревью изменений в рабочей копии (`git status`, `git diff`):
- [`services/rich_converter.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/services/rich_converter.py#L228-L260)
- [`templates/d2_quill_include.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L80-L320)
- [`tests/services/test_rich_converter.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/services/test_rich_converter.py#L184-L277)
- [`docs/exec-plans/active/2026-10-16-d2-datauri-paste-publish-fail.md`](file:///home/itolstov/Projects/mtl/eurmtl.me/docs/exec-plans/active/2026-10-16-d2-datauri-paste-publish-fail.md)
- Контекст: [`routers/decision.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L1239-L1277), [`templates/d2_form.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_form.html), [`templates/d2_question.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_question.html).

---

## Находки по приоритетам

### P1 (критичные баги — чинить до коммита)
*Критичных дефектов, приводящих к падению, утечкам данных или уязвимостям безопасности, не обнаружено.*  
Код прошел 7 кругов проработки, краевые случаи (гонки курсора, многофайловая загрузка, `disable_fields`, `dragover` в Firefox, отмена сабмита по Enter во время upload) закрыты и проверены смоуком.

---

### P2 (стоит поправить перед коммитом)

1. **[`docs/drafts/agy_d2_datauri_paste_review.md:1`](file:///home/itolstov/Projects/mtl/eurmtl.me/docs/drafts/agy_d2_datauri_paste_review.md#L1)**  
   **Суть**: В рабочей копии присутствует пустой untracked-файл размером 0 байт.  
   **Почему**: В плане ([строка 48](file:///home/itolstov/Projects/mtl/eurmtl.me/docs/exec-plans/active/2026-10-16-d2-datauri-paste-publish-fail.md#L48)) на него есть ссылки как на черновик ревью, однако сам файл пуст. При случайном или массовом `git add` пустой файл попадет в коммит.  
   **Как чинить**: Записать в файл итоговые заметки ревью либо удалить пустой файл перед коммитом (`rm docs/drafts/agy_d2_datauri_paste_review.md`).

2. **[`tests/routers/test_d2_publish.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_d2_publish.py)**  
   **Суть**: Отсутствует сквозной интеграционный тест публикации вопроса с `data:image/...` в BODY.  
   **Почему**: Инцидент №705 произошел именно в пайплайне публикации (`POST /d2/<uuid>/publish` → [`_d2_send_rich`](file:///home/itolstov/Projects/mtl/eurmtl.me/routers/decision.py#L315) → `sendRichMessage`). В диффе добавлены детальные unit-тесты для [`services/rich_converter.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/services/rich_converter.py), но в [`test_d2_publish.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_d2_publish.py) нет регрессионного теста на уровне роутера, фиксирующего, что вопрос с data-URI публикуется без исключений и без photo-блока.  
   **Как чинить**: Добавить в [`tests/routers/test_d2_publish.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_d2_publish.py) тест (например, `test_d2_publish_with_data_uri_body_skips_photo_and_succeeds`), проверяющий успешный вызов `send_rich_message` без падения на legacy-фолбэк.

---

### P3 (вкусовщина и мелкие улучшения)

1. **[`services/rich_converter.py:236-252`](file:///home/itolstov/Projects/mtl/eurmtl.me/services/rich_converter.py#L236-L252)**  
   **Суть**: Избыточные/повторные проверки в ветвлении [`_photo_block`](file:///home/itolstov/Projects/mtl/eurmtl.me/services/rich_converter.py#L228).  
   **Почему**: Сначала проверяется `if is_http: ...`, затем отдельным условием `if not (is_http or is_root_relative): return None`, а затем еще раз тернарный оператор `src if is_http else ...`.  
   **Как чинить**: Сделать линейный `if-elif-else`:
   ```python
   if is_http:
       try:
           if not urlsplit(src).netloc:
               return None
       except ValueError:
           return None
       media = src
   elif is_root_relative:
       media = f"{base_url.rstrip('/')}/{src.lstrip('/')}"
   else:
       return None
   ```

2. **[`templates/d2_quill_include.html:207`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L207)**  
   **Суть**: Переменная `var d2UploadsInFlight = 0;` объявлена на строке 207, но используется выше на [строке 86](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L86) внутри `form.onsubmit`.  
   **Почему**: Благодаря JavaScript-хостингу `var` код работает корректно во время выполнения сабмита, но чтение кода сверху вниз вызывает когнитивную нагрузку из-за разрыва в 120 строк.  
   **Как чинить**: Перенести объявление `var d2UploadsInFlight = 0;` вверх скрипта (перед функциями `d2InitQuill` / `d2SetFormBusy`).

3. **[`templates/d2_quill_include.html:139`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L139)**  
   **Суть**: Проверка MIME-типа в [`d2ExtractImages`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L131) через жесткий регэксп `/^(image\/(png|jpe?g|webp|gif))$/i`.  
   **Почему**: Если браузер передаст параметры в заголовке типа (например, `image/png; charset=...`), регэксп не сработает (хотя в [строке 240](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L240) и на бэкенде в `routers/decision.py:1250` используется отсечение параметров `.split(';')[0]`).  
   **Как чинить**: Использовать `var mime = (file.type || '').split(';')[0].trim().toLowerCase();` и сверять с whitelist либо расширить регэксп до `/^image\/(png|jpe?g|webp|gif)(;|$)/i`.

4. **[`templates/d2_quill_include.html:283,288`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L283)**  
   **Суть**: Двойная проверка `targetIndex !== null && targetIndex !== undefined`.  
   **Почему**: В JS стандартная идиома `targetIndex != null` эквивалентна проверке на оба значения.  
   **Как чинить**: Заменить на `targetIndex != null`.

---

## Что упростить

1. **Ветвление в [`services/rich_converter.py:236-252`](file:///home/itolstov/Projects/mtl/eurmtl.me/services/rich_converter.py#L236-L252)**: избавиться от каскада условий с `not (is_http or is_root_relative)` и финального тернарника, перейдя на прямой `if is_http: ... elif is_root_relative: ... else: return None`.
2. **Проверки `null`/`undefined` в [`templates/d2_quill_include.html`](file:///home/itolstov/Projects/mtl/eurmtl.me/templates/d2_quill_include.html#L283)**: заменить повторяющиеся громоздкие условия `targetIndex !== null && targetIndex !== undefined` на краткое `targetIndex != null`.

---

## Чего не хватает в тестах

1. **Интеграционный тест роутера публикации ([`tests/routers/test_d2_publish.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/routers/test_d2_publish.py))**:
   - Публикация вопроса, содержащего `<img src="data:image/png;base64,...">` в BODY: проверить, что Telegram API `send_rich_message` вызывается успешно, не падает в legacy fallback и формирует список блоков без photo-блока.
2. **Дополнительные краевые случаи в [`tests/services/test_rich_converter.py`](file:///home/itolstov/Projects/mtl/eurmtl.me/tests/services/test_rich_converter.py)**:
   - Относительный путь без ведущего слэша: `<p><img src="pic.jpg"></p>` или `<p><img src="images/pic.jpg"></p>` (код дропает их по задумке, но отдельного теста нет).
   - Тег с пустым или состоящим из пробелов `src`: `<p><img src="   "></p>`.
   - Вставка `data:` внутри `<blockquote>` и `<blockquote class="d2-expandable">`: убедиться, что цитата не ломается и текст сохраняется.
   - Смешанный параграф с несколькими картинками: `<p><img src="data:..."><img src="/d2/img/1"><img src="blob:..."></p>` — проверка, что валидное фото строится, а мусорные отбрасываются.

---

## Вердикт

**чинить и коммитить** *(устранить P2: удалить пустой `docs/drafts/agy_d2_datauri_paste_review.md`, добавить интеграционный тест в `test_d2_publish.py` и применить упрощения P3)*.
