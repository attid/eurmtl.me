# D2: покрытие тестами забытых роутов

Дата: 2026-10-15. Статус: в работе.

## Контекст

Инцидент 2026-10-15: `GET /d2/copy` падал 500 с 9 октября
(`UndefinedError: 'readings_total' is undefined`, фикс `38e0864`). Причина
пробоя: у `/d2/copy` не было ни одного теста. Аудит показал ещё три роута без
покрытия: `POST /d2/template/from`, `GET /d2/number`, отказные ветки
`GET/POST /d2/<uuid>`.

Цель: закрыть тестами все d2-роуты, оставшиеся без покрытия, в стиле
существующих d2-тестов (фикстуры `tests/routers/test_d2_workspace.py`).

## Скоуп

Новый файл `tests/routers/test_d2_copy_template.py`:

1. `/d2/copy` (uuid PFM-вопроса, воркспейс PFM):
   - 200, тело содержит «(копия)», `name="reading"` (радио чтений),
     «Копия вопроса №1»;
   - левый uuid → 404;
   - вопрос невидимой орги → 404 (юзер без подписантства/секретарства).
2. `/d2/template/from` (POST):
   - сохранение: `post_data` в `QUESTION_TEMPLATES` с TITLE/BODY исходника,
     редирект на `/d2/<uuid>`;
   - пустой title в форме → берётся TITLE вопроса;
   - левый uuid → 404.
3. `/d2/number`:
   - без воркспейса в сессии → `{"number": "1"}`;
   - воркспейс GORA с вопросами №№ 1, 2 → следующий номер орги
     (`_org_next_number` по questions орги).
4. `/d2/<uuid>` отказные:
   - левый uuid → 404;
   - uuid существующий, но орга невидима → 404.

Вне скоупа: POST-логика чтений/черновиков (покрыта
`test_reading_autostatus.py`, `test_d2_publish.py`), картинки
(`test_d2_images.py`), фильтры списка (`test_d2_filters.py`).

## Приёмо-сдаточные

- `uv run --extra dev pytest tests/routers/test_d2_copy_template.py` — зелёный.
- Релевантные d2-файлы не деградировали; `ruff check`, `ruff format --check`,
  `pyright` на новых файлах чисто.
- Регрессия инцидента: тест `/d2/copy` на коде до `38e0864` падает (проверено
  смоуком при фиксе), после — зелёный.

## Паттерны

- Хелперы `_login`, `_set_org`, `_secretaries_mock`, `_user_org_names_mock`,
  `_tables_mock`, `_seed_questions`, константы адресов из
  `tests/routers/test_d2_workspace.py` — импортировать, не копировать.
- Горячие кеши (`org_signers_cache`, `secretary_ids_cache`) — автозёз-фикстура
  уже в `test_d2_workspace`, при импорте хелперов подтянется.
