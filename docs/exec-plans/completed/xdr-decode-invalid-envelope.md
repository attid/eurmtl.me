# Invalid XDR Decode Handling

## Контекст
`POST /lab/xdr_to_json` падал с `500`, если входная строка формально проходила дальше, но не являлась валидным Stellar XDR. На входе `AAAA` `stellar_sdk` выбрасывал `EOFError` во время распаковки envelope, и ошибка уходила наружу без нормализации.

## Выполненные изменения
1. [x] Добавлен регресс-тест для `POST /lab/xdr_to_json` с ожиданием ответа `400` и текста ошибки `Invalid Stellar XDR`.
2. [x] Добавлен сервисный тест, фиксирующий контролируемый `ValueError` для обрезанного XDR.
3. [x] Минимально обновлен `services/xdr_parser.py`: `EOFError` теперь нормализуется в `ValueError("Invalid Stellar XDR")`, а `decode_xdr_to_base64()` использует общий helper `_parse_transaction_envelope()`.
4. [x] Минимально обновлен `routers/laboratory.py`, чтобы `POST /lab/xdr_to_json` возвращал `400`, а не `500`, при ошибке декодирования XDR.

## Риски и замечания
- Изменение намеренно не расширялось на другие маршруты и не тянуло рефакторинг большого `services/xdr_parser.py`.
- Сигнал ошибки сохранен явным: вызывающий код получает `ValueError("Invalid Stellar XDR")` вместо необработанного исключения из `stellar_sdk`.

## Верификация
- `just check-changed`
- `uv run pytest tests/services/test_xdr_parser.py tests/routers/test_laboratory.py --no-cov -q`
