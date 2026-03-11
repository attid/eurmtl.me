# Coverage To Sixty

## Контекст
Локальный детерминированный baseline на 2026-03-07:
- `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev pytest -m 'not integration' --cov-report=term-missing:skip-covered --maxfail=1 -q`
- Результат: `210 passed, 1 deselected`, `TOTAL 40.24%`

До `60%` не хватает примерно 955 покрытых строк, поэтому мелких точечных тестов недостаточно. Нужны крупные deterministic unit-тесты по модулям с высокой плотностью логики и минимальной зависимостью от сети/teardown.

## План изменений
1. [ ] Обновить сервисные тесты для `services/xdr_parser.py`:
   - `decode_xdr_to_base64`
   - `decode_scval`
   - `update_memo_in_xdr`
   - ветки `LiquidityPoolAsset` / claimable balance payload
2. [ ] Обновить сервисные тесты для `services/stellar_client.py`:
   - `process_xdr_transaction`
   - `decode_asset`
   - `decode_flags`
   - `add_trust_line_uri`
   - `xdr_to_uri`
3. [ ] Расширить async-сервисные тесты для `services/stellar_client.py`:
   - `get_available_balance_str`
   - `check_asset`
   - `_fetch_account` / `get_offers`
   - `get_fund_signers`
   - `stellar_build_xdr` с моками `Server`, `pay_divs`, `get_pool_data`, `stellar_copy_multi_sign`
4. [ ] После каждого блока запускать только релевантные тесты без coverage.
5. [ ] В конце запустить coverage-прогон `-m 'not integration'` и измерить фактический прирост.

## Риски и открытые вопросы
- `60%` может потребовать второй итерации даже после больших сервисных тестов.
- Полный `pytest` в sandbox упирается в сетевой integration-тест `tests/test_extract_sources.py::test_horizon_account_response_format`.
- Изменения production-кода допустимы только если TDD/проверка вскроют реальный дефект, а не ради процентов.

## Верификация
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/services/test_xdr_parser.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/services/test_stellar_client.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/services/test_stellar_client_async.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache uv run --extra dev pytest -m 'not integration' --cov-report=term-missing:skip-covered --maxfail=1 -q`
