## Context

`/lab` не импортирует XDR с операцией `PathPaymentStrictSend`, хотя серверный декодер распознает такой XDR. Текущий frontend ожидает форму операции `swap`.

## Goal

Сделать так, чтобы `decode_xdr_to_base64(..., return_json=True)` возвращал для `PathPaymentStrictSend` payload, совместимый с существующим lab-импортом `swap`.

## Files

- `services/xdr_parser.py`
- `tests/services/test_xdr_parser.py`

## Plan

1. Добавить регрессионный тест на сериализацию `PathPaymentStrictSend` в формат, совместимый с `swap`.
2. Минимально адаптировать сериализацию в `services/xdr_parser.py` без изменения остальных операций.
3. Прогнать точечные тесты для подтверждения фикса.
