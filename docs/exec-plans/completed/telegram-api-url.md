# telegram-api-url: Configurable Telegram Bot API endpoint

## Контекст
Нужна возможность указать альтернативный Telegram Bot API (self-hosted или proxy)
через переменную окружения `TELEGRAM_API_URL`. Если переменная не задана — используется
официальный `https://api.telegram.org`.

Дополнительно: в `other/telegram_tools.py` есть прямые REST-вызовы в `api.telegram.org`
(`send_telegram_message_`, `edit_telegram_message_`, `is_user_admin`). Они обходят aiogram
и дублируют его функциональность. По решению: оставить единый канал работы с Telegram —
через aiogram.

## План изменений
1. [x] `other/config_reader.py` — добавить поле `telegram_api_url: str = "https://api.telegram.org"`.
2. [x] `other/telegram_tools.py`:
   - [x] Фабрика `Bot`, которая при нестандартном `telegram_api_url` создаёт
         `AiohttpSession(api=TelegramAPIServer.from_base(url))`.
   - [x] Лог `Using custom Telegram Bot API URL: <url>` при нестандартном URL.
   - [x] Удалены неиспользуемые `send_telegram_message_` и `edit_telegram_message_`.
   - [x] `is_user_admin` переписан через `skynet_bot.get_chat_member`
         (нормализация `chat_id` к `-100...`, `False` при ошибке).
   - [x] `is_bot_admin` — тонкая обёртка поверх `is_user_admin`.
   - [x] Убран импорт `http_session_manager`.
3. [x] `tests/test_telegram_tools.py`:
   - [x] Удалён тест `test_send_and_edit_telegram_message_helpers`.
   - [x] `test_is_user_admin_formats_chat_id_and_handles_failure` переписан на мок
         `skynet_bot.get_chat_member`.
4. [x] `just check` — тесты зелёные (270 passed, coverage 63.52%); ruff/pyright на
      изменённых файлах чистые.

## Риски и открытые вопросы
- Совместимость aiogram 3.21 API `TelegramAPIServer.from_base` / `AiohttpSession` — проверено,
  импорты доступны.
- `is_bot_admin` в `routers/web_editor.py` передаёт положительный `chat_id`; нормализация
  к `-100...` должна сохраниться, иначе прод-поведение изменится.

## Верификация
- `just check` зелёный.
- Новые/обновлённые тесты в `tests/test_telegram_tools.py` покрывают `is_user_admin`
  через моки aiogram.
- Ручная сверка: в `other/telegram_tools.py` нет упоминаний `api.telegram.org` кроме
  дефолта в конфиге.
