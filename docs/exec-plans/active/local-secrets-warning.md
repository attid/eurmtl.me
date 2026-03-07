# Local Secrets Warning

## Контекст
Локальный запуск pytest показывает `UserWarning: directory "/run/secrets" does not exist` из `pydantic-settings`. В production `secrets_dir` нужен, но локально директория часто отсутствует и только шумит в выводе.

## План изменений
1. [ ] Добавить тест на вычисление `secrets_dir` для случаев, когда `/run/secrets` есть и когда его нет.
2. [ ] Минимально обновить `other/config_reader.py`, чтобы `secrets_dir` подключался только при существующей директории.
3. [ ] Прогнать точечный тест и `check-changed`.

## Риски и открытые вопросы
- Не сломать production-путь чтения секретов из `/run/secrets`.
- Не вносить глобальное подавление warnings в pytest, если можно убрать причину.

## Верификация
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_config_reader.py -q --no-cov`
- `UV_CACHE_DIR=/tmp/uv-cache just check-changed`
