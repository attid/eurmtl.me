import re

import requests
from config_reader import config
import urllib.parse
import hmac
import hashlib


def send_telegram_message(chat_id, text, entities=None):
    """
    Sends a Telegram message to the specified chat.

    Parameters:
        chat_id (int): The ID of the chat to send the message to.
        text (str): The text of the message.
        entities (list, optional): A list of message entities to be applied to the text (default: None).

    Returns:
        int: The ID of the sent message.
    """
    token = config.skynet_token.get_secret_value()
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': text
    }
    if entities:
        data['entities'] = entities
    else:
        data['parse_mode'] = 'HTML'

    response = requests.post(url, json=data)
    if response.ok:
        #print(f'Sending message: {data}')
        #print(f'Message sent successfully: {response.json()}')
        return response.json()['result']['message_id']
    else:
        print(f'Failed to send message: {response.content}')


def edit_telegram_message(chat_id, message_id, text, reply_markup=None, entities=None):
    """
    Edit a message in the Telegram chat.

    Parameters:
        chat_id (int): The ID of the chat where the message is located.
        message_id (int): The ID of the message to be edited.
        text (str): The new text of the message.
        reply_markup (Optional[Any]): Optional parameter. The reply markup of the message.
        entities (Optional[Any]): Optional parameter. The entities of the message.

    Returns:
        bool: True if the message was edited successfully, False otherwise.
    """
    token = config.skynet_token.get_secret_value()
    url = f'https://api.telegram.org/bot{token}/editMessageText'
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text
    }

    if reply_markup:
        data['reply_markup'] = reply_markup

    if entities:
        data['entities'] = entities
    else:
        data['parse_mode'] = 'HTML'

    response = requests.post(url, json=data)
    if response.ok:
        # print(f'Sending message: {data}')
        # print(f'Message sent successfully: {response.json()}')
        return True
    else:
        print(f'Failed to edit message: {response.content}')
        return False


def is_bot_admin(chat_id):
    """
    Проверяет, является ли бот администратором в чате.
    :param chat_id: ID чата.
    :return: True, если бот является администратором, иначе False.
    """
    token = config.skynet_token.get_secret_value()
    return is_user_admin(chat_id, token.split(':')[0])  # user_id бота можно получить из его токена


def is_user_admin(chat_id, user_id):
    """
    Проверяет, является ли пользователь администратором в чате.
    :param chat_id: ID чата.
    :param user_id: ID пользователя.
    :return: True, если пользователь является администратором, иначе False.
    """
    if str(chat_id).startswith('-100'):
        pass
    else:
        chat_id = f'-100{chat_id}'
    token = config.skynet_token.get_secret_value()
    url = f'https://api.telegram.org/bot{token}/getChatMember'
    params = {
        'chat_id': chat_id,
        'user_id': user_id
    }
    response = requests.get(url, params=params)
    if response.ok:
        chat_member = response.json()['result']
        return chat_member['status'] in ['administrator', 'creator']
    else:
        print(f'Ошибка при проверке статуса пользователя: {response.content}')
        return False


def check_response(data):
    d = data.copy()
    del d['hash']
    d_list = []
    for key in sorted(d.keys()):
        if not d[key] is None:
            d_list.append(key + '=' + d[key])
    data_string = bytes('\n'.join(d_list), 'utf-8')

    bot_secret_key = hashlib.sha256(config.bot_token.get_secret_value().encode('utf-8')).digest()
    hmac_string = hmac.new(bot_secret_key, data_string, hashlib.sha256).hexdigest()
    if hmac_string == data['hash']:
        return True
    return False


def prepare_data_check_string(query_string):
    # Разбираем query string в словарь
    data = urllib.parse.parse_qs(query_string, keep_blank_values=True)
    hash_value = data.pop('hash', [None])[0]

    # Сортируем данные и формируем строку для проверки подписи
    sorted_data = sorted((k, v[0]) for k, v in data.items())
    check_data_string = '&'.join(f'{k}={v}' for k, v in sorted_data).replace('&', '\n')

    return hash_value, check_data_string


def is_hash_valid(hash_value, check_data_string, token):
    # Создаем секретный ключ
    secret_key = hmac.new("WebAppData".encode(), token.encode('utf-8'), hashlib.sha256).digest()
    # Вычисляем хеш
    calculated_hash = hmac.new(secret_key, check_data_string.encode('utf-8'), hashlib.sha256).hexdigest()
    return calculated_hash == hash_value


def check_response_webapp(data):
    hash_value, check_data_string = prepare_data_check_string(data)
    result = is_hash_valid(hash_value, check_data_string, config.skynet_token.get_secret_value())
    return result


if __name__ == '__main__':
    pass
