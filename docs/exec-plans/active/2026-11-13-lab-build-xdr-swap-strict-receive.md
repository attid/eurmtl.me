# 2026-11-13 — Lab: сборка и импорт `PathPaymentStrictReceive` (`swap_strict_receive`)

## Контекст

`/lab` умеет собирать только `PathPaymentStrictSend`: UI-блок `swap`, ветка
сборщика `operation["type"] == "swap"` и таблица валидации payload содержат
только strict send. `PathPaymentStrictReceive` поддерживается лишь текстовым
декодом (`/remote/decode`), и там подпись операции инвертирована.

Проверено по коду:

- `services/stellar_client.py:1024-1042` — единственная path-payment ветка:
  `append_path_payment_strict_send_op(...)`.
- `routers/laboratory.py:164-170` — в `_BUILD_XDR_FIELDS` только `"swap"`.
- `services/xdr_parser.py:266-284` — `PathPaymentStrictSend` → `name: "swap"`;
  `PathPaymentStrictReceive` попадает в `else` → `{"detail": "Unsupported operation type"}`.
- `static/js/main.js:1268-1270` (`getCardByName`) — карточки для strict receive
  нет, поэтому импорт такого XDR молча пропускает операцию.
- `routers/laboratory.py:731-750` — подбор пути только через
  `strict_send_paths` (сумма трактуется как отправляемая).
- `templates/tabler_laboratory.html:45,114` — в списках операций только `swap`.
- `static/js/laboratory.js` не подключён ни в одном шаблоне (мёртвый файл);
  живой UI — `static/js/main.js`.

## Согласованное решение

1. Новый тип операции payload: `swap_strict_receive` (алиасы только на
   импорте/`getCardByName`: `swapStrictReceive`, `pathPaymentStrictReceive`).
2. Форма payload зеркалит существующий `swap`, чтобы не заводить новый
   словарь полей:
   - `selling` — send asset;
   - `buying` — destination asset;
   - `amount` — **dest_amount** (точная сумма к получению);
   - `destination` — **send_max** (максимум, что готовы отдать);
   - `path` — JSON-строка массива ассетов (тот же формат, что у `swap`).
3. Получатель — как у `swap`: `sourceAccount` операции, иначе top-level
   `publicKey`. Третьим лицам path payment из лабы по-прежнему не строим.
4. `swap` (strict send) не меняется по поведению и payload.
5. Подбор пути входит в объём работ: `strict_receive_paths()` — другой
   эндпоинт Horizon и другая база суммы, иначе путь и сумма не совпадают.
   Выбор подсказки заполняет и `path`, и `send_max`.
6. Текстовый декод strict receive исправляется рядом (суммы/ассеты были
   перепутаны).

## Изменения

- `services/stellar_client.py` — хелпер разбора `path` (вынесен из ветки
  `swap`) и ветка `swap_strict_receive` →
  `append_path_payment_strict_receive_op(...)`.
- `routers/laboratory.py` — запись `swap_strict_receive` в
  `_BUILD_XDR_FIELDS` (kind'ы как у `swap`) и роут
  `GET /lab/path_receive/<asset_from>/<asset_for>/<asset_sum>` на
  `strict_receive_paths()`.
- `services/xdr_parser.py` — JSON-декод `PathPaymentStrictReceive` →
  `swap_strict_receive`; исправлена текстовая подпись операции. Рядом
  исправлен `path` в JSON-декоде (был `Asset.to_dict()` с `type/code/issuer`,
  теперь сериализуется в формат Horizon `asset_type/asset_code/asset_issuer`
  строкой JSON — иначе импортированный `swap` не проходил валидацию
  `build_xdr` и не мог собраться обратно).
- `static/js/main.js` — `generateCardSwapStrictReceive()`, `fetchPathReceive()`,
  `showPathReceiveDropdown()` (клик ставит `path` + `send_max`), ветки в
  `getCardByName()`.
- `templates/tabler_laboratory.html` — опция «Swap (strict receive)» в табах
  «Платежи» и «All»; cache-busting `main.js`.
- `templates/llm.txt` — контракт операции `swap_strict_receive`.
- `tests/routers/test_laboratory.py` — сборка XDR (позитив/негатив) и роут
  подбора пути.
- `tests/services/test_xdr_parser.py` — round-trip strict receive XDR →
  `swap_strict_receive` + текстовая подпись.
- `tests/live/test_lab_horizon_live.py` — живые e2e-тесты против публичного
  Horizon (маркер `live`, запуск `just test-live` / `RUN_LIVE_TESTS=1`):
  path_receive и path на реальном аккаунте фонда, сборка XDR -> декод ->
  повторная сборка, кастомный `sourceAccount`, текстовый декод, мусорный
  asset. Только GET, без `submit`. Сейчас 7 тестов.
- `docs/conventions.md` и `AGENTS.md` — правило: мок-тест не считается
  доказательством совместимости с внешним API, нужен живой e2e.
- `pytest.ini` — маркер `live`; `justfile` — рецепт `test-live`.
- `docs/exec-plans/completed/2026-05-03-lab-import-path-payment-strict-send.md`
  — перенос из `active/` (задача выполнена: сериализация и тест есть).

## Follow-up (отдельная сессия, решение владельца)

- Вырезать моки из тестов полностью и свести всё в один `just test`: снять
  маркер `live` в `pytest.ini`, гейт `RUN_LIVE_TESTS` в
  `tests/live/test_lab_horizon_live.py` и рецепт `test-live` в `justfile`,
  перенести живой набор в общий прогон. Отдельный live-набор — временное
  решение, а не целевое.

## Проверки

- `just fmt`, `just lint`, `just types`
- `uv run --extra dev pytest tests/routers/test_laboratory.py tests/services/test_xdr_parser.py -q`
- `just test-fast`, `just arch-test`

## Результаты ревью (agy, круг 1)

Отчёт: `docs/drafts/agy_lab_swap_strict_receive_round1_review.md`.

- P1 `/lab/path_receive` всегда отдавал `{}`: `strict_receive_paths()` ждёт
  `str | List[Asset]`, а получал одиночный `Asset` → `TypeError` в
  `convert_assets_to_horizon_param()`, который съедал `except`. FIXED: список
  + тест на аргументы вызова билдера.
- P2 мёртвое кэширование в `fetchPathReceive` (запись в `globalCash` без
  чтения). FIXED: кэш убран (пути не кэшируем — ликвидность меняется).
- P2 коллизия ключей, когда несколько маршрутов дают одинаковый
  `source_amount`. FIXED: в лейбл добавлен маршрут (`direct` / `via USD`),
  дубли получают суффикс, тест есть.
- P3 `path` длиннее 5 элементов проходил валидацию и падал `ValueError` в
  `to_xdr()` (500 вместо 400). FIXED: проверка длины в `_is_swap_path()`,
  тест есть.
- P3 пробелы в asset-полях ломали `decode_asset`. FIXED: `$.trim()` в
  `fetchPathReceive`.
- P3 дублирование кода позиционирования dropdown (`showDropdown`,
  `showOfferDropdown`). OUT OF SCOPE (backlog): рефакторинг чужих
  dropdown-ов в этот дифф не тащим.

### Круг 2 (отчёт `…_round2_review.md`)

- P2 native-хоп в `path` (`{"asset_type": "native"}`) выпадал из лейбла
  маршрута и давал ложный `direct`. FIXED: `item.get("asset_code") or "XLM"`,
  тест есть.
- P3 мёртвая проверка `$('#' + dropdownId).length` в
  `showPathReceiveDropdown`. FIXED: удалена.
- P3 нет `.trigger('change')` при подстановке `send_max`. FIXED.
- Упрощения: `record.get(...) or "XLM"`, `asset.type` в `serialize_path`,
  `Asset.native()` в `_decode_asset_path`.
- Тесты: native-хоп в лейбле, нечисловой `asset_sum`, сборка с native
  в `path`, декод `StrictReceive` с выпущенным активом в `path`.

### Круг 3 (финальный, `…_round3_review.md`)

P1/P2/P3 — нет; вердикт ревьювера: `коммитить`.

## Пост-ревью: почему P1 проскочил и что сделано

Первый P1 (`strict_receive_paths` получал одиночный `Asset` -> `TypeError` ->
`{}`) не был пойман, потому что тест подменял весь `Server` на `MagicMock`:
он проверял «я вызвал мок так, как сам придумал», а не «SDK принимает такие
аргументы». Плюс поверил типу `Union[str, List[Asset]]` и не прошел в
`convert_assets_to_horizon_param()`, а живого e2e теста не было.

Сделано:

- `tests/live/test_lab_horizon_live.py` — живые тесты на реальном аккаунте
  фонда (`main_fund_address`, пара XLM -> EURMTL): path_receive и path отдают
  пути, strict send и strict receive считают разные стороны суммы, сборка
  XDR -> декод -> повторная сборка, кастомный `sourceAccount`, текстовый
  декод, мусорный asset → `{}`.
- По новому правилу `AGENTS.md` (запрет моков) новые тесты этого PR
  переписаны без подмен: лейблы маршрутов проверяются на чистой функции
  `_path_receive_label()`, валидация — прямыми вызовами
  `validate_build_xdr_payload()`, интеграция — живым `tests/live`.
  Сборка XDR вне сети (`patch("stellar_sdk.Server.load_account")`) в этом PR
  не делается: владелец разрешение не дал, офлайн-прогон не нужен.
  Решение владельца: моков в тестах быть не должно вообще (старые будут
  вырезаны отдельной сессией), проверка — живая (`just test-live`).
- Гейт: маркер `live` + `RUN_LIVE_TESTS=1` (обычный `pytest` их пропускает,
  сеть в CI не нужна), рецепт `just test-live`, правило в `docs/conventions.md`.
- Проверено: `just test-live` — 7 passed на живом Horizon.

## Ручная проверка

1. Lab → «Платежи» → «Swap (strict receive)»: заполнить selling/buying,
   «Amount to receive», нажать 🔍 — выбрать подсказку, проверить, что
   подставились `path` и «Maximum send amount».
2. «Get XDR» → «Decode to Text» — операция описывается как получение
   `dest_asset` и отправка `send_asset`.
3. «Импортировать операции» из собранного XDR — блок восстанавливается с теми
   же полями (round-trip).
