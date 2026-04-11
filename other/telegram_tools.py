import hashlib
import hmac
import logging
import urllib.parse

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from sulguk import AiogramSulgukMiddleware

from other.config_reader import config

logger = logging.getLogger(__name__)

_DEFAULT_TELEGRAM_API_URL = "https://api.telegram.org"
_TELEGRAM_API_URL = config.telegram_api_url.rstrip("/")

if _TELEGRAM_API_URL != _DEFAULT_TELEGRAM_API_URL:
    logger.info("Using custom Telegram Bot API URL: %s", _TELEGRAM_API_URL)


def _build_bot(token: str) -> Bot:
    if _TELEGRAM_API_URL == _DEFAULT_TELEGRAM_API_URL:
        return Bot(token=token)
    session = AiohttpSession(api=TelegramAPIServer.from_base(_TELEGRAM_API_URL))
    return Bot(token=token, session=session)


skynet_bot = _build_bot(config.skynet_token.get_secret_value())
mmwb_bot = _build_bot(config.mmwb_token.get_secret_value())
skynet_bot.session.middleware(AiogramSulgukMiddleware())
mmwb_bot.session.middleware(AiogramSulgukMiddleware())


async def is_bot_admin(chat_id):
    """Проверяет, является ли бот администратором в чате."""
    return await is_user_admin(chat_id, skynet_bot.id)


async def is_user_admin(chat_id, user_id):
    """Проверяет, является ли пользователь администратором в чате."""
    normalized_chat_id = (
        chat_id if str(chat_id).startswith("-100") else f"-100{chat_id}"
    )
    try:
        chat_member = await skynet_bot.get_chat_member(
            chat_id=normalized_chat_id, user_id=user_id
        )
        return chat_member.status in ("administrator", "creator")
    except Exception as e:
        print(f"Error checking user admin status: {e}")
        return False


def check_response(data, token=None):
    if token is None:
        token = config.mmwb_token.get_secret_value()

    d = data.copy()
    del d["hash"]
    d_list = []
    for key in sorted(d.keys()):
        if d[key] is not None:
            d_list.append(key + "=" + d[key])
    data_string = bytes("\n".join(d_list), "utf-8")

    bot_secret_key = hashlib.sha256(token.encode("utf-8")).digest()
    hmac_string = hmac.new(bot_secret_key, data_string, hashlib.sha256).hexdigest()
    if hmac_string == data["hash"]:
        return True
    return False


def prepare_data_check_string(query_string):
    # Разбираем query string в словарь
    data = urllib.parse.parse_qs(query_string, keep_blank_values=True)
    hash_value = data.pop("hash", [None])[0]

    # Сортируем данные и формируем строку для проверки подписи
    sorted_data = sorted((k, v[0]) for k, v in data.items())
    check_data_string = "&".join(f"{k}={v}" for k, v in sorted_data).replace("&", "\n")

    return hash_value, check_data_string


def is_hash_valid(hash_value, check_data_string, token):
    # Создаем секретный ключ
    secret_key = hmac.new(
        "WebAppData".encode(), token.encode("utf-8"), hashlib.sha256
    ).digest()
    # Вычисляем хеш
    calculated_hash = hmac.new(
        secret_key, check_data_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return calculated_hash == hash_value


def check_response_webapp(data, config_token=config.skynet_token):
    hash_value, check_data_string = prepare_data_check_string(data)
    result = is_hash_valid(
        hash_value, check_data_string, config_token.get_secret_value()
    )
    return result


def prepare_html_text(text: str) -> str:
    """
    Prepares HTML text by replacing <p> tags with <div> tags.

    Args:
        text (str): The input HTML text.

    Returns:
        str: The modified HTML text with <p> tags replaced by <div> tags.

    Note:
        This function performs a simple string replacement and does not parse the HTML.
        It may not handle all cases correctly if the input is complex or malformed HTML.
    """
    if not isinstance(text, str):
        raise TypeError("Input must be a string")
    text = text.replace("<p>", "<div>")
    text = text.replace("</p>", "</div>")

    return text


# Optional: Add a simple test
def test_prepare_html_text():
    input_text = "<p>Hello</p><p>World</p>"
    expected_output = "<div>Hello</div><div>World</div>"
    assert prepare_html_text(input_text) == expected_output, "Test failed"
    print("Test passed")


# Uncomment the following line to run the test
# test_prepare_html_text()

if __name__ == "__main__":
    pass
    test_prepare_html_text()
