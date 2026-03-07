# Invalid XDR Decode Handling

## Контекст
`POST /remote/decode` падает с `500`, если строка является валидным base64, но невалидным Stellar XDR. Регресс воспроизводится входом из `1.txt`, где `stellar_sdk` выбрасывает `ValueError` во время распознавания envelope.

## План изменений
1. [x] Добавить регресс-тест для `POST /remote/decode` с XDR из `1.txt` и ожидаемым ответом `400`.
2. [x] Добавить сервисный тест, который фиксирует контролируемый `ValueError` для невалидного Stellar XDR.
3. [x] Минимально обновить `services/xdr_parser.py`, чтобы ошибки парсинга envelope приводились к понятному `ValueError`.
4. [x] Минимально обновить `routers/remote.py`, чтобы `POST /remote/decode` возвращал `400`, а не `500`, при ошибке декодирования XDR.
5. [x] Прогнать точечные тесты для `tests/services/test_xdr_parser.py` и `tests/routers/test_remote.py`.

## Риски и открытые вопросы
- В проекте есть другие вызовы `decode_xdr_to_text`; изменение должно сохранить для них явный сигнал об ошибке, а не маскировать проблему.
- Нельзя расширять дифф на несвязанные рефакторинги в большом `services/xdr_parser.py`.

## Верификация
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/services/test_xdr_parser.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache /usr/bin/timeout 20s uv run pytest tests/routers/test_remote.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache just check-changed`
