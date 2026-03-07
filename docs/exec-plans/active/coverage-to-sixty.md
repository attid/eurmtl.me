# Coverage To Sixty

## Контекст
Текущее общее покрытие около 37%. Цель — быстро и безопасно поднять его примерно до 60%, выбирая зоны с максимальной отдачей на один написанный тест и избегая хрупкой глубокой эмуляции тяжёлых модулей.

## План изменений
1. [ ] Добавить unit-тесты для `other/grist_cache.py`, чтобы закрыть инициализацию кеша, индексы, фильтры и обновление по webhook.
2. [ ] Расширить `tests/routers/test_remote_sep07.py` для веток parse/add/get/submit-signed и ошибок валидации.
3. [ ] Расширить `tests/routers/test_grist.py` для позитивных и негативных веток webhook/groups/menu.
4. [ ] Расширить `tests/routers/test_laboratory.py` для JSON/XDR helpers и дополнительных endpoint-веток.
5. [ ] Добавить точечные сервисные тесты для `services/transaction_service.py` на недокрытые permission/status ветки.
6. [ ] После каждого блока запускать релевантные тесты и в конце проверить общее покрытие.

## Риски и открытые вопросы
- До 60% может понадобиться несколько итераций; точный прирост заранее не гарантирован.
- Роутовые тесты в этом проекте местами зависают на teardown клиента, поэтому для локальной диагностики может понадобиться `timeout`.
- Нельзя компенсировать проценты искусственными тестами без смысла; прирост должен идти через реальные ветки поведения.

## Верификация
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_grist_cache.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/routers/test_remote_sep07.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/routers/test_grist.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/routers/test_laboratory.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/services/test_transaction_service.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache just check-changed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run coverage report -m`
