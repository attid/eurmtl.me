# 2026-10-22 — Валидация payload `POST /lab/build_xdr` (Sentry #3123)

## Контекст

Sentry #3123 (Docker3, диагностика №89): `POST /lab/build_xdr` упал с
`AttributeError: 'dict' object has no attribute 'split'`.
Трассировка: `routers/laboratory.py:136` (`stellar_build_xdr(data)`) →
`services/stellar_client.py:915` (payment) → `decode_asset()`
`services/stellar_client.py:836`.

Внешний JSON-клиент передал asset объектом: `{"code": "'XLM'"}`.
`decode_asset()` ожидает строку `XLM` или `CODE-ISSUER` и делает
`asset.split("-")`, поэтому объект дал `AttributeError` → необработанный 500.

## Причина

Маршрут `POST /lab/build_xdr` передавал тело запроса в
`services.stellar_client.stellar_build_xdr()` без проверки типов. Сборщик
XDR читает поля «как есть» (`operation["asset"]`, `len(operation["limit"])`,
`float2str(operation["amount"])`, `int(operation["offer_id"])`,
`json.loads(operation["path"])`), поэтому любое поле неправильного типа
давало необработанное исключение (`AttributeError`, `TypeError`,
`IndexError`, `ValueError`, `KeyError`) и HTTP 500.

## Согласованное решение

1. Объектная (dict) форма asset **не поддерживается** и не конвертируется:
   контракт остаётся строковым (`XLM` или `CODE-ISSUER`).
2. Валидация типов/форматов выполняется на границе API — в
   `routers/laboratory.py`, до вызова сборщика XDR. Ошибка → HTTP 400
   `{"error": "<поле>: <ожидание> (got <тип>)"}`.
3. Stellar-бизнес-логика (`services/stellar_client.py`) не меняется:
   корректные payload'ы проходят без изменений.
4. Проверяются все поля маршрута, которые сборщик читает и приводит к
   числу/строке/JSON, а также вложенные структуры (`swap.path`,
   `create_claimable_balance.claimant_*`, `revoke_sponsorship.*`).

## Изменения

- `routers/laboratory.py` — декларативная таблица типов полей операций
  (`_BUILD_XDR_FIELDS`, `_REVOKE_SPONSORSHIP_FIELDS`) и валидаторы
  `validate_build_xdr_payload()`, `_validate_build_xdr_operation()`,
  `_validate_claimants()`, `_check_payload_field()`. В `cmd_build_xdr()`
  добавлены: проверка «тело — JSON-объект» и вызов валидатора перед
  `stellar_build_xdr()`. Формат asset проверяется тем же `decode_asset()`
  (dry-run в `try/except`), чтобы семантика совпадала со сборщиком.
  Для чисел два вида: `number` (как `float2str()` — запятая как разделитель
  допустима) и `float` (как `float()` — без запятой, `inf`/`nan`), потому что
  `pay_divs`, `liquidity_pool_*` и `create_account.startingBalance` приводят
  значения строже. Вид `amount` у `liquidity_pool_withdraw` уточняется
  динамически (`_validate_liquidity_pool_withdraw`): `float()` там только при
  нулевом минимуме, иначе `float2str()`. Элемент `swap.path` обязан содержать
  строковый `asset_type` — сборщик читает `asset["asset_type"]` всегда.
- `tests/routers/test_laboratory.py` — регрессионные тесты: dict-asset
  (кейс Sentry), нестроковые/некорректные asset, не-объектное тело,
  отсутствие `publicKey`/`operations`, `operations` не массивом, элемент
  операции не объектом, числовые поля неправильного типа, `limit`/`data_value`
  объектом, `swap.path` (не JSON / не массив / элемент без issuer),
  предикаты claimable balance, `revoke_sponsorship`, а также позитивные
  кейсы (валидные payload'ы по-прежнему 200).
- `docs/architecture.md` — правило «payload'ы API валидируются на границе,
  неправильный тип → 400, объектная форма asset не поддерживается».
- `templates/llm.txt` — в разделе `POST /lab/build_xdr` зафиксирован формат
  ответа 400 на невалидные типы/форматы.

## Что НЕ меняется

- Контракт корректных запросов: те же поля, те же форматы, тот же ответ
  `{"xdr": ...}`; `stellar_build_xdr()` и `decode_asset()` не изменены.
- Проверка `memo_hash` остаётся с прежним кодом ответа (200 +
  `{"error": "Bad memo hash..."}`), чтобы не ломать существующий контракт
  и тест; добавлена только защита от нестрокового `memo` (раньше `500`).
- Неизвестный (строковый) тип операции по-прежнему игнорируется — как в
  `stellar_build_xdr()`; ошибкой это не становится.
- Нестрогие к типу поля, которые сборщик игнорирует (`sourceAccount`,
  `revoke_type`), не отклоняются — поведение сохранено. Исключение —
  `require_trustline`/`requireTrustline` у `pay_divs`: отклоняется только
  переполнение (`int(inf)`), остальные значения работают как раньше
  (см. «Раунд 2»).
- `services/`, `db/`, `other/` не меняются. Соседний роут
  `/remote/sep07/submit-signed` (SSRF, Sentry #3121) — вне объёма.

## Проверки

- `pytest tests/routers/test_laboratory.py -q --no-cov`.
- Полный `just test` (или `pytest` из `.venv`), `just fmt`, `just lint`,
  `just types`, `just arch-test`.

## Раунд 1 Code Review — TРЕБУЮТСЯ ИСПРАВЛЕНИЯ → исправлено

Замечания ревьювера и что сделано:

1. **P1 `swap.path`**: валидатор принимал элемент без `asset_type`, если
   `asset_code`/`asset_issuer` валидны; сборщик всё равно читает
   `asset["asset_type"]` → `KeyError` → 500. Теперь `asset_type` обязателен и
   должен быть строкой (`_is_swap_path`); добавлены регрессионные тесты
   `swap-path-missing-asset-type` и `swap-path-asset-type-not-string` (400 +
   сборщик не вызывается) и позитивный real-build тест `swap`.
2. **P1 `liquidity_pool_withdraw.amount`**: вид `float` был слишком строгим —
   `amount="1,5"` при ненулевых минимумах корректен (сборщик идёт через
   `float2str()`). Теперь `amount` — `number`, а при нулевом минимуме
   динамически ужесточается до `float` (`float(amount)` для share_ratio).
   Тесты: `withdraw-comma-amount-zero-min` → 400; реальная сборка с
   `amount="1,5"`, `min_amount_a="1"`, `min_amount_b="1"` → 200, XDR содержит
   `amount="1.5"`, `get_pool_data` не вызывался.
3. **P2 `_is_int`**: не перехватывался `OverflowError` (`1e999` → `inf` →
   `int(inf)`), т.е. `sequence`/`bump_to` роняли сам валидатор в 500. Добавлено
   `OverflowError`; тесты `sequence-overflow` и `bump-to-overflow` (сырой JSON
   `1e999`) → 400, сборщик не вызывается.

Дополнительно (по замечанию «позитивные тесты подменяют весь сборщик»)
добавлены router-level тесты с **реальной сборкой** и замоканным Horizon:
`payment` (XDR декодируется, `Payment`), `liquidity_pool_withdraw` (см. выше)
и `swap` (`PathPaymentStrictSend`, path `["XLM","EUR"]`, `dest_min="0.5"`).

## Раунд 2 Code Review — P2 (pay_divs require_trustline) → исправлено

Замечание: в `pay_divs` валидатор не проверял `require_trustline` и его алиас
`requireTrustline`. Сборщик делает `int(raw_flag)` и ловит только
`TypeError`/`ValueError`, поэтому JSON `1e999` → `inf` → `int(inf)` →
`OverflowError` → HTTP 500.

Исправлено: `_validate_pay_divs()` (вызывается из
`_validate_build_xdr_operation` для `pay_divs`) повторяет выбор поля из
сборщика (`require_trustline`, если ключ есть, иначе `requireTrustline`) и
отклоняет **только** переполнение — HTTP 400
`operations[0].<field> is out of range for an integer (got inf)`.
Остальные значения сохранены как были: нечисловые/нестроковые по-прежнему
откатываются в `true` внутри сборщика, `null`/отсутствие поля — значение по
умолчанию; затенённый алиас (при заданном `require_trustline`) не проверяется,
т.к. сборщик его не читает и `OverflowError` там невозможен.

Тесты: `require_trustline` и `requireTrustline-alias` с сырым JSON `1e999` →
400 и сборщик не вызывается; `shadowed_pay_divs_alias_overflow` → 200
(поведение сохранено); параметризованные позитивы (`"1"`, `"0"`, `1`, `0`,
мусорная строка, `null`, алиас, отсутствие поля) → 200;
реальная сборка `pay_divs` с замоканными `load_account`/`pay_divs` → 200,
XDR содержит `Payment`, `require_trustline=False` для `requireTrustline: "0"`.

## Результаты проверок

- `pytest tests/routers/test_laboratory.py -q --no-cov` — **81 passed**
  (было 19; добавлено 62 кейса: dict-asset из Sentry #3123, матрица
  невалидных типов, numeric overflow (включая `pay_divs`
  `require_trustline`/`requireTrustline`), 4 теста реальной сборки XDR с
  замоканным Horizon, позитивные payload'ы). Покрытие валидатора в
  `routers/laboratory.py` — построчно 100% (кроме двух осознанных
  `pragma: no cover`: опечатка в таблице и защитная ветка порядка проверок).
- Полный `pytest` — **753 passed, 1 skipped**, coverage 71.9% (порог 30%).
- `ruff format --check .` — 111 files already formatted; `ruff check .` -
  All checks passed.
- `pyright --pythonpath .venv/bin/python` — **0 errors** (без явного
  интепретатора pyright в этой песочнице не видит site-packages и шумит
  `reportMissingImports` — окружение, не код).
- `.linters/arch_test.py` — passed.
- Штатные `just *` в этой песочнице не запускаются: `just` есть, но в
  PATH нет `uv` (`sh: 1: uv: not found`), поэтому выполнены эквивалентные
  команды из `.venv`.

## Отдельные находки (вне объёма правок)

- `templates/llm.txt` описывал `limit`, `threshold`, `weight`, `setFlags`,
  `clearFlags` как `optional`, хотя `stellar_build_xdr()` читает их через
  `operation[...]` и падает `KeyError` при отсутствии. Валидатор следует
  коду, а документация приведена в соответствие (`required by current
  code`). Отдельного решения требует только вопрос, надо ли этим полям
  быть по-настоящему необязательными (изменение бизнес-логики — вне
  задачи).

## Риски и открытые вопросы

- Таблица `_BUILD_XDR_FIELDS` — зеркало полей сборщика: при добавлении новой
  операции в `stellar_build_xdr()` её нужно добавить и сюда (иначе для неё
  останется старое поведение «500 на неправильный тип»). Неизвестные типы
  валидатор не проверяет намеренно.
- `routers/rely.py:513` тоже вызывает `stellar_build_xdr()` без валидации —
  вне объёма задачи (не `/lab/build_xdr`); отмечено как отдельное замечание.
- Не проверяется существование аккаунтов/ассетов (сетевые проверки остаются
  за Horizon), только типы и форматы. `publicKey`/`destination` проверяются
  как строки (не как 56-символьный ключ): формат аккаунта по-прежнему
  валидирует `stellar_sdk`/Horizon — поведение для таких ошибок не менялось.
- Строгость изменилась только для мусорных значений, которые и раньше не
  могли дать XDR: нестроковый/пустой `type` (раньше молча игнорировался, 200
  с пустой транзакцией), отсутствующие обязательные поля (раньше `KeyError`
  → 500), объектные/числовые значения там, где сборщик делает
  `len()`/`int()`/`float2str()` (раньше `TypeError`/`ValueError` → 500).
  Ни один корректный запрос не отклоняется.
- Нестрогие к типу поля, которые сборщик читает через `.get()`
  (`sourceAccount`, `revoke_type`), намеренно не валидируются — поведение
  «молча игнорируется» сохранено. У `pay_divs` `require_trustline` /
  `requireTrustline` проверяется только на переполнение, т.к. сборщик
  приводит значение через `int()` и не ловит `OverflowError`.
