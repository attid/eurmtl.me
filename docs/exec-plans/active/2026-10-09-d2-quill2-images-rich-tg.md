# D2: Quill 2 + картинки (Grist Attachments) + Rich-Telegram

Дата: 2026-10-09 · Статус: план, ждёт GO ·
Заказчик: владелец. Блокеры пила (вместе с задачей 3 — док `3Fk4hjCv847GBx8ZTCPN2Y` уже вписан, `e66db0a`).

## Context — решения владельца (2026-10-09, вечер)

1. **Картинки — по уму в Grist** (Attachments), не на диске.
2. **TG умеет картинки в тексте** (Rich Messages, Bot API 10.x) — владелец дал эталон:
   выгрузка канала 64Gram → `docs/samples/tg_rich_message_example.json` (коммит `7e9d7db`).
   27 постов, блоки: heading/paragraph/photo/list/table; текст: plain/bold/italic/
   concat/text_link/math/code/sup/sub. 319 photo-блоков — картинки прямо в тексте.
3. **aiogram поднят до 3.31.0** (пин, коммит `7e70a40`) — `SendRichMessage`,
   `InputRichMessage`, все `InputRichBlock*` уже есть. 503 passed.
4. **Эмодзи-кнопка — в беклог** (владелец: «отложить, сделать след этапом»):
   quill-emoji 0.2.0 несовместим с Quill 2; юникод-эмодзи в тексте работают и так.
   В тулбаре кнопку убрать (d2_*; легаси `/d` и web_editor не трогаем).
5. **Никаких миграционных скриптов; сайт никогда не создаёт схему Grist.**
   Таблицу аттачментов создаёт владелец руками в UI до выката (я дам ему точную
   схему колонок), приложение только пишет данные.

## Задача A — Quill 2.x + картинки (Grist Attachments)

1. **Quill 2 локально**: `static/js/quill.js` + `static/css/quill.snow.css` (2.x,
   скачать в репо, CDN из d2_form/d2_question убрать — заодно уходим от CDN).
2. **quill-emoji убрать из d2-шаблонов** (d2_form/d2_question/d2_quill_include):
   кнопку из тулбара, скрипт, css. Легаси-шаблоны (tabler_decision, decision,
   web_editor) не трогать — там Quill 1 остаётся.
3. **Загрузка картинки**: тулбар-кнопка «🖼» → file input → POST `/d2/upload_image`
   (гейт `_d2_edit_allowed(org)` воркспейса) → сервер кладёт файл в Grist
   Attachments-таблицу `D2_IMAGES` (док `3Fk4hjCv847GBx8ZTCPN2Y`; колонки:
   `FILE` (attachment), `ORG`, `UPLOADED_BY`, `CREATED_AT`; таблицу создаёт
   владелец руками до выката — дать ему схему) → ответ `{url}` → вставка
   `<img src="{url}">` в Quill.
4. **Отдача картинок**: роут `GET /d2/img/<attachment_id>` — прокси к Grist
   (`GET /docs/{doc}/attachments/{id}`), кеш-заголовки, публичный (картинки
   читают анонимы из TG-поста; секретов в картинках вопросов нет).
5. **Ограничения**: max 5 МБ, jpg/png/webp/gif; лимит в разумных пределах на
   вопрос (напр. 10 картинок) — soft, клиентом.
6. **Тесты**: upload (гейт, размер, тип), img-роут, квилл-инициализация не
   ломается (smoke на стенде скрином).

## Задача B — Rich-Telegram (конвертер Quill Delta → InputRichMessage)

1. **Конвертер** `services/rich_converter.py`: Quill Delta (что хранит Quill 2
   в `QUESTION_DATA.BODY` — сейчас HTML; перейти на Delta JSON с миграцией
   формата вручную при переносе, либо парсить существующий HTML через
   BeautifulSoup → блоки; решение внутри задачи, owner не против).
   Маппинг: header → heading (level 1-3), абзац → paragraph, list → list,
   bold/italic/code/link → текстовые узлы, `<img>` → photo (по attachment id).
   Эталон формата: `docs/samples/tg_rich_message_example.json`.
2. **Публикация**: `sendRichMessage` (aiogram 3.31) в канал орги вместо
   `sendMessage`+SULGUK; правка — `editMessageText(rich_message=...)`.
   Черновик — без TG (уже так). Републикация мёртвого поста — новый
   sendRichMessage.
3. **sulguk в d2 убрать** (в легаси остаётся: web_editor, /d).
4. **Фолбэк**: если конвертер не справился (незнакомый блок) — пост как сейчас
   (HTML/SULGUK) + лог warning. Пилот не блокируем.
5. **Тесты**: конвертер (маппинг каждого блока по эталону), send/edit вызовы
   (моки), фолбэк.

## Порядок: A → B → ручное создание D2_IMAGES владельцем → пилот (задача 3).

## Verification

- `uv run pytest tests/ --no-cov -q` — 0 failed (после каждой задачи).
- Стенд: создать вопрос с картинкой → /dev/tg-log показывает rich_message c
  photo-блоком; правка → edit с rich_message; скрины Quill 2 тулбара владельцу.
- Ручное: владелец создаёт таблицу `D2_IMAGES` в доке (схема из задачи A.3).
