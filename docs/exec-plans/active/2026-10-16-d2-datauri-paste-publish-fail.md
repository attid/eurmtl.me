# 2026-10-15/16 — Публикация №705 упала: data-URI картинка из буфера

## Контекст инцидента

`cmd_d2_add` (вопрос №705 [PFM], QUESTION_ID=1032): `sendRichMessage` →
`Bad Request: failed to get HTTP URL content`, фолбэк `sendMessage` →
`text is too long`. Итог: `telegram_link=None`, вопрос/чтение сохранены,
пост в Telegram не ушёл.

Причина: пользователь вставил скриншот из буфера (Ctrl+V) — Quill 2
вставил `<img src="data:image/png;base64,...">` (135 402 символа из
136 142 BODY). `_photo_block` (`services/rich_converter.py:227`) строит
photo-блок с `_absolute_url` → `https://eurmtl.me/data:image/png;base64,...`
— Telegram-сервер не может скачать. Legacy-фолбэк падает на лимите 4096.

## Согласованное решение (владелец: «ок давай 1+2»)

1. **Paste-handler в Quill**: перехват вставки изображений из буфера →
   тот же путь, что кнопка 🖼: `POST /d2/upload_image` → Grist Attachments
   → `<img src="/d2/img/<id">`. Закрывает источник data-URI.
2. **Guard в `_photo_block`**: `data:`-URI не превращаем в photo-блок
   (блок пропускается, конвертация не падает). Гарантия: существующие и
   будущие кривые BODY деградируют до «пост без картинки», а не до
   «публикация упала». Дропнутое фото остаётся в Grist-версии BODY.

## Изменения

- `services/rich_converter.py` — `_photo_block`: `data:`/нечитаемые URI → `None`.
- `tests/services/test_rich_converter.py` — кейс data-URI (нет photo-блока).
- `templates/d2_quill_include.html` — paste-listener: `clipboardData`
  image → upload; НЕ-image paste не трогаем (Quill по умолчанию).
- Include инлайнится серверно в `templates/d2_form.html:166` и
  `templates/d2_question.html:258` — кеш-бастинг не нужен (отдельных
  статических файлов не появилось).

## Приёмо-сдаточные

- `pytest tests/services/test_rich_converter.py tests/routers -q` — зелёный,
  кейсы: data-URI дропается (в т.ч. DATA:/Data: — RFC 3986), инлайн
  data-URI в абзаце, валидная картинка рядом с data-URI.
- Браузерный смоук: вставка PNG из буфера в Quill на /d2 → `POST
  /d2/upload_image` → `<img src="/d2/img/...">` в HTML (не data-URI),
  курсор за картинкой, multi-file последовательно, пустое имя файла
  (Safari) получает фолбэк `pasted_<ts>.png`, сабмит-кнопки дисейблятся
  на время загрузки.
- `ruff check`, `ruff format --check` на изменённых файлах; arch-test.

## Раунды ревью (agy, docs/drafts/agy_d2_datauri_paste_review.md)

Круг 1 — исправлено: P1 filename-фолбэк в FormData; P2 src.lower(); P2
курсор после insertEmbed; P2 последовательная multi-file загрузка; P2
блокировка submit во время upload. Отклонено: P3 deleteText при вставке
поверх выделения (нативное поведение paste-замены Quill, менять не
просили); P3 Array.from (сделано попутно).

Круг 2 — исправлено: P1 разблокировка серверно-задизейбленных кнопок
(disable_fields): busy помечает только свои кнопки dataset.uploadDisabled,
серверные не трогает; P2 busy-счётчик на всю пачку (d2UploadImages) —
кнопка не мигала активной между файлами; P2 guard расширен до whitelist
http(s)/относительных src (blob: из drop тоже дропается); P2 проверка
d2UploadsInFlight в form.onsubmit (Enter-сабмит в обход disabled-кнопки);
P2 drop-обработчик картинок (capture на quill.container); P3 расширение
фолбэка по file.type. Смоук: drop-картинка → attachment, серверная
кнопка после busy-цикла остаётся disabled, jpeg без имени → pasted_*.jpeg.

Круг 3 — исправлено: P1 d2PickImage переведён на d2UploadImages
(busy-блокировка теперь и для кнопки 🖼; смоук: busyNow=true, after=false,
attachment); P2 _absolute_url регистронезависим (HTTPS:// не превращается
в относительный путь); P2 protocol-relative //host дропается (битый URL);
P3 paste/drop унифицированы (d2ExtractImages + d2BindFilePaste, −25 строк).
Отклонено: P2 вставка drop в точку курсора мыши (caretRangeFromPoint) —
ограничение задокументировано в комментарии, вставка в позицию курсора
редактора приемлема; P3 draft-файл (не пустой — отчёт, drafts коммитятся
исторически). Тесты +4: uppercase-схема сохраняется, //host, top-level
img, img в li. Итог: 312 passed.

Круг 4 — исправлено: P2 dragover preventDefault (types=Files; иначе
Firefox отменяет drop/открывает файл во вкладке); P3 фолбэк по расширению
имени при пустом file.type; P3 alert-агрегация на пачку (один alert в
finally); P3 комментарий-ограничение drop-в-курсор-редактора; P3
quill.enable(false) при data-disabled. P2 рассинхрон курсора: первая
попытка (заморозка enable(false) на время upload) откачена — смоук
показал, что замороженный Quill молча пропускает insertEmbed; заменено
на перечитывание selection после upload. Смоук: печать во время upload —
обе картинки на местах (attachments 7-8).

Круг 5 — исправлено: P1 drop не-изображения при cancelable dragover
уводил браузер на file:// (потеря черновика) — drop теперь всегда
preventDefault при Files; P2 пустой file.type в multipart падал 400
unsupported type — Blob с MIME по расширению; P2 paste/drop в read-only
редакторе грузил мусор на сервер — guard quill.isEnabled(); P2
getSelection(true) крал фокус из полей формы — без true, чужой фокус
возвращается после insertEmbed (он в Quill 2 перетягивает фокус);
P3 getLength()-1 для вставки за последний \n; P3 декомпозиция условия
guard в _photo_block; P3 грязное расширение file.type с параметрами.
Смоуки: txt-drop prevented, no upload; notype.png (пустой type, имя
.pong) принят сервером; фокус возвращён в short_subject; в редакторе
курсор за картинкой (index 1); nope.png при enable(false) не дошёл до
сервера (grep 0). Итог: 312 passed, ruff чист.

Круг 6 — исправлено: P1 paste без preventDefault (убран при унификации
круга 3) — WebKit/Firefox сами вставляли data-URI поверх загрузки;
возвращён + смоук pastePrevented=true; P1 регрессия кнопки 🖼 (фокус на
тулбаре → range null → вставка в конец): d2PickImage сохраняет курсор
до диалога (getSelection(true)) и передаёт targetIndex через
d2UploadImages → d2UploadImageFile, вставка на сохранённый индекс
(смоук: imgAtStart=true); P3 MIME для имени без точки ("screenshot" →
image/screenshot, 400): ext только при наличии точки; P3
quill.isEnabled() в d2PickImage; P3 http:// без хоста дропается
(urlsplit().netloc, тест scheme_without_host); упрощение: _absolute_url
удалена, media собирается в _photo_block (единственный вызов).
Отклонено: P2 «пустой draft-файл» — ложь (12201 байт, agy видит файл в
момент `>` обнуления перед записью). Итог: 313 passed.

Круг 7 — P1 нет (вербатим: «критичных дефектов не обнаружено»).
Исправлено: P2 ValueError на битых IPv6 ("http://[invalid") — urlsplit
в try/except, дроп картинки вместо 500 (тест invalid_ipv6);
P2 whitelist MIME в d2ExtractImages по D2_IMAGE_TYPES (SVG/TIFF не
шлются на сервер; смоук: svg paste — не preventDefault, 0 аплоадов,
обычный PNG прошёл); P2 комментарий/имя: is_root_relative, политика
"относительные пути без / не поддерживаются" зафиксирована в
комментарии; P3 безопасный file.type. Итог: 314 passed.

Круг 8 — P1 нет. Исправлено: P2 интеграционный тест в
tests/routers/test_d2_publish.py (test_add_publish_with_data_uri_body_
skips_photo: BODY с data-URI → rich-публикация без photo-блока, легаси
не нужен — регрессия инцидента №705 на уровне роутера); P3 линейное
if/elif/else в _photo_block ( media собирается в ветках, без тернарника);
P3 hoisting: var d2UploadsInFlight перенесён в начало скрипта; P3
MIME-параметры ("image/png; charset=...") отсекаются split(';') как
бэкенд (смоук: param.png прошёл, x.svg мимо); P3 targetIndex != null;
+5 краевых тестов конвертера (без слэша, пустой src, blockquote,
смешанный параграф). «Пустой draft-файл» — та же ложь (agy читает файл
в момент `>` обнуления; 10536 байт). Итог: 319 passed, ruff/ruff-format
чисто, JS syntax OK, смоуки формы зелёные.

Сходимость достигнута: круги 7 и 8 подряд без P1 (критерии скилла —
обычно 2–4 круга, здесь 8 из-за регрессий, вносимых самими фиксами
предыдущих кругов).

## Не входит (отдельно, по команде)

- Починка BODY №705 (перекодировка уже сохранённого data-URI в
  Attachments) — вариант 3.
- Проверка/повторная публикация №705 в Telegram.
