# W6a: черновик вопроса + публикация/републикация

## Задача
- Пустой `TELEGRAM_LINK` в `QUESTION_DATA` = черновик.
- Чекбокс «Сохранить как черновик» в форме создания: без `send_message` в TG,
  `TELEGRAM_LINK` остаётся пустым; `QUESTIONS` + `QUESTION_DATA` пишутся как сейчас.
- Бейдж «черновик» в списке `/d2/fragment/edit`.
- Кнопка «Опубликовать» на экране вопроса `/d2/<uuid>`: POST `/d2/<uuid>/publish`.
  - Пустой `TELEGRAM_LINK` → `send_message` (`get_full_text`, `chat_ids[reading]`)
    → patch `TELEGRAM_LINK`.
  - Непустой `TELEGRAM_LINK` → сначала `edit_message_text` по старому
    message_id; TG «message to edit not found» → `send_message` нового поста +
    patch `TELEGRAM_LINK`.
  - Результат через flash + redirect на `/d2/<uuid>`.
- Право: секретари через `get_secretaries()` (grist `EURMTL_secretaries`, doc
  `3Fk4hjCv847GBx8ZTCPN2Y`). В тест-режиме кеш не инициализируется →
  `load_secretaries_from_grist()` через `grist_manager.load_table_data` напрямую:
  EURMTL_secretaries → account → users telegram_id. Сид получает заглушку:
  секретарь с telegram_id 1837984392 (itolstov, тест-юзер).
- Кнопка ТОЛЬКО секретарю и пока вопрос в черновике; после публикации кнопка не
  рендерится (мёртвый пост ловится POST'ом по ошибке TG).

## Файлы
- `routers/decision.py` — чекбокс в `/d2/add`, роут `/d2/<uuid>/publish`,
  хелперы секретарей, флаги для шаблонов.
- `templates/d2_form.html` — только чекбокс черновика (больше форму не трогать —
  решение владельца).
- `templates/d2_question.html` — кнопка «Опубликовать» (секретарь+черновик).
- `templates/d2_edit_fragment.html` — бейдж «черновик» в списке.
- `tests/fixtures/d2_stand_seed.json` — таблицы EURMTL_secretaries/accounts/users
  для стенда.
- `tests/routers/test_d2_publish.py` — тесты publish-роута и черновика.

## Constraints
- Не коммитить, не пушить, сервер на :8000 не поднимать.
- ruff format + ruff check перед сдачей.
- Форму создания не менять besides чекбокса.

## Приёмка
- POST /d2/add с черновиком → в /dev/tg-log пусто.
- Список показывает бейдж «черновик».
- POST /d2/<uuid>/publish секретарём → sendMessage в tg-log, ссылка заполнена.
- Повторный publish → editMessageText.
- Publish не-секретарём → 403/flash.
