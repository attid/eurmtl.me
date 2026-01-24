# Тесты eurmtl.me

Руководство по запуску и написанию тестов для проекта eurmtl.me.

## Быстрый старт

```bash
# Запустить все тесты
just test
# или
uv run pytest

# Запустить тесты с подробным выводом
uv run pytest -v

# Запустить конкретный тест
uv run pytest tests/test_qr_tools.py::TestQRTools::test_decode_color_valid_hex

# Запустить только быстрые unit-тесты (без интеграционных)
uv run pytest -m "not integration"

# Запустить только интеграционные тесты
uv run pytest -m integration
```

## Структура тестов

```
tests/
├── fixtures/              # Организованные фикстуры
│   ├── __init__.py       # Экспорт фикстур
│   ├── constants.py      # Константы для тестов
│   ├── app.py            # Фикстуры Quart приложения
│   └── horizon.py        # Mock Stellar Horizon сервера
├── routers/              # Тесты роутов (endpoints)
│   ├── test_index.py
│   ├── test_sign_tools.py
│   └── ...
├── services/             # Тесты сервисов
│   └── test_transaction_service.py
├── conftest.py           # Главный файл конфигурации pytest
└── test_*.py             # Unit-тесты утилит
```

## Coverage (покрытие кода)

Проект настроен на измерение покрытия кода тестами с помощью `pytest-cov`.

```bash
# Запустить тесты с отчётом о покрытии (автоматически при pytest)
uv run pytest

# Просмотреть HTML отчёт
open htmlcov/index.html
# или на Linux
xdg-open htmlcov/index.html
```

**Текущее покрытие:** ~34%  
**Минимальный порог:** 30%

### Цели по покрытию:
- **Критичные модули** (services/, db/): стремиться к 80%+
- **Роуты** (routers/): стремиться к 60%+
- **Утилиты** (other/): стремиться к 50%+

## Фикстуры

### Основные фикстуры

#### `app` - тестовое Quart приложение
```python
@pytest.mark.asyncio
async def test_something(app):
    async with app.app_context():
        # ваш код с доступом к app
```

#### `client` - тестовый клиент
```python
@pytest.mark.asyncio
async def test_endpoint(client):
    response = await client.get("/")
    assert response.status_code == 200
```

#### `mock_horizon` - mock Stellar Horizon сервера
```python
@pytest.mark.asyncio
async def test_with_horizon(mock_horizon, horizon_server_config):
    # Настройка mock аккаунта
    mock_horizon.set_account(
        "GABC...",
        balances=[{"asset_type": "native", "balance": "100.0"}]
    )
    
    # ваш тест
```

### Константы (из `fixtures/constants.py`)

```python
from tests.fixtures.constants import (
    ADMIN_USER_ID,           # '84131737'
    REGULAR_USER_ID,         # '12345'
    TEST_FUNDED_ACCOUNT,     # Тестовый Stellar аккаунт
    TEST_SECRET_KEY,         # 'test_secret_key'
)
```

## Написание тестов

### Соглашения об именовании

**Файлы:** `test_<module_name>.py`  
**Классы:** `Test<FeatureName>` (опционально, для группировки)  
**Функции:** `test_<что_тестируем>_<условие>_<ожидаемый_результат>`

Примеры:
```python
def test_decode_color_valid_hex():
    """Тест декодирования валидного HEX цвета"""
    
def test_sign_tools_add_post_success():
    """Тест POST /sign_tools с успешным результатом"""

def test_should_return_404_when_transaction_not_found():
    """BDD-стиль: должен вернуть 404 когда транзакция не найдена"""
```

### Асинхронные тесты

Используйте декоратор `@pytest.mark.asyncio` для async функций:

```python
@pytest.mark.asyncio
async def test_async_function(client):
    response = await client.get("/api/data")
    assert response.status_code == 200
```

### Параметризованные тесты

Для тестирования нескольких входных данных:

```python
@pytest.mark.parametrize("color,expected", [
    ("FFFFFF", (255, 255, 255)),
    ("000000", (0, 0, 0)),
    ("FF0000", (255, 0, 0)),
])
def test_decode_color(color, expected):
    assert decode_color(color) == expected
```

### Мокирование

Используйте `unittest.mock.patch` для подмены зависимостей:

```python
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
@patch("routers.index.get_ip", new=AsyncMock(return_value="127.0.0.1"))
async def test_myip(client):
    response = await client.get("/myip")
    assert (await response.get_data(as_text=True)) == "127.0.0.1"
```

### Интеграционные тесты

Помечайте интеграционные тесты маркером:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_horizon_api():
    """Тест с реальным Horizon API"""
    # этот тест выполняет реальные HTTP запросы
```

## Частые проблемы

### 1. Тесты падают с ошибкой "RuntimeError: no running event loop"

**Решение:** Добавьте декоратор `@pytest.mark.asyncio`:
```python
@pytest.mark.asyncio
async def test_my_async_function():
    ...
```

### 2. Фикстура не найдена

**Причина:** Фикстура не импортирована в `conftest.py`  
**Решение:** Проверьте, что фикстура экспортируется из нужного модуля

### 3. Тесты проходят локально, но падают в CI

**Возможные причины:**
- Зависимости от локальных файлов
- Разные часовые пояса
- Внешние API недоступны

**Решение:** Используйте моки для внешних зависимостей

## Best Practices

1. **Один тест - одна проверка:** Тест должен проверять только одну вещь
2. **AAA паттерн:** Arrange (подготовка) → Act (действие) → Assert (проверка)
3. **Независимость:** Тесты не должны зависеть друг от друга
4. **Быстрота:** Unit-тесты должны выполняться быстро (<1s каждый)
5. **Читаемость:** Имена тестов должны объяснять, что тестируется
6. **Моки для IO:** Всегда мокируйте сеть, БД, файловую систему в unit-тестах

## Полезные команды

```bash
# Запустить только упавшие тесты
uv run pytest --lf

# Остановить на первой ошибке
uv run pytest -x

# Показать print() в выводе
uv run pytest -s

# Запустить тесты параллельно (требует pytest-xdist)
uv run pytest -n auto

# Обновить список зависимостей
uv sync
```

## Ресурсы

- [Pytest документация](https://docs.pytest.org/)
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [Stellar SDK документация](https://stellar-sdk.readthedocs.io/)
