# Lab build XDR missing memo_type

## Контекст

`POST /lab/build_xdr` падал с `500` и `KeyError: 'memo_type'`, если клиент отправлял JSON без поля `memo_type`.

Контракт в `templates/llm.txt` описывает `memo_type` как optional, но код обращался к нему как к обязательному полю:

- `routers/laboratory.py` проверял `data["memo_type"]` до вызова builder.
- `services/stellar_client.py` повторял такое же обращение внутри `stellar_build_xdr()`.

## Выполненные изменения

1. [x] Добавлен regression-тест для `POST /lab/build_xdr` без `memo_type`.
2. [x] Добавлен сервисный regression-тест для `stellar_build_xdr()` без `memo_type`.
3. [x] Обновлен `routers/laboratory.py`: memo type читается через `data.get("memo_type", "")`, а `memo_hash` валидируется только если явно выбран.
4. [x] Обновлен `services/stellar_client.py`: memo добавляется только для явных `memo_text` и `memo_hash`; отсутствие `memo_type` больше не падает.

## Риски и замечания

- Изменение не меняет публичный контракт: оно приводит реализацию к уже описанному optional-поведению.
- Валидация `memo_hash` сохранена на уровне router.
- Остальная логика сборки XDR не рефакторилась.

## Верификация

- RED: новые тесты до правки падали с `KeyError: 'memo_type'`.
- `uv run --extra dev pytest tests/routers/test_laboratory.py::test_lab_build_xdr_accepts_missing_memo_type tests/services/test_stellar_client.py::TestBuildXdr::test_stellar_build_xdr_accepts_missing_memo_type -q --no-cov`: passed, 2 tests.
- `uv run --extra dev pytest tests/routers/test_laboratory.py tests/services/test_stellar_client.py -q --no-cov`: passed, 46 tests.
- `just check-changed`: passed.
