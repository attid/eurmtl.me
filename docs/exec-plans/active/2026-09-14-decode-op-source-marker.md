# Decode: operation source marker only for explicit op source

## Goal

В `decode_xdr_to_text` строка `*** для аккаунта ...` печатается для каждой операции,
подставляя сурс транзакции, если у операции нет своего. Вернуть исходное поведение:
строка печатается только когда у операции есть явный `operation.source`.

## Root cause

- Исходное поведение: `215337c` (`utils.py`) - строка под `if operation.source:`.
- Регрессия: `ab39899` (SimulatedLedger) заменил условие на фолбэк к сурсу транзакции
  и безусловный вывод. Сейчас: `services/xdr_parser.py`, цикл в `decode_xdr_to_text`.

## Scope

1. [x] `services/xdr_parser.py`: обернуть вывод `*** для аккаунта` (и загрузку баланса
   для него) в `if operation.source:`. `op_source_id` с фолбэком оставить - он нужен
   дальше по коду для проверок баланса/симуляции.
2. [x] `tests/services/test_xdr_parser.py`: регресс-тест - конверт из двух SetOptions
   (без сурса и с сурсом); маркер встречается ровно один раз и только для операции
   с явным сурсом.
3. [x] Прогнать целевые тесты и `just check-changed`.

## Out of scope

- JSON-декод (`decode_xdr_to_base64`): ключ `sourceAccount: null` писался и до
  регрессии; поведение не менялось оптимизациями.

## Verification

- RED: новый тест падает на текущем коде (маркер печатается дважды, первый раз с
  сурсом транзакции).
- GREEN: тест проходит после фикса.
- `uv run --extra dev pytest tests/services/test_xdr_parser.py -q --no-cov`
- `just check-changed`

## Result

- RED: `test_decode_xdr_to_text_marks_source_only_for_explicit_op_source` упал на
  старом коде (`assert 2 == 1`, маркер печатался с сурсом транзакции).
- GREEN: после фикса тест проходит.
- `uv run --extra dev pytest tests/services/test_xdr_parser.py tests/test_stellar_tools_extra.py -q --no-cov`: 50 passed.
- `just check-changed`: passed (format + lint).
- `just arch-test`: passed.
