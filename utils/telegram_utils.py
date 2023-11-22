import requests
from config_reader import config


def send_telegram_message(chat_id, text):
    token = config.skynet_token.get_secret_value()
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'  # Опционально: для форматирования текста
    }
    response = requests.post(url, data=data)
    if response.ok:
        # print(f'Message sent successfully: {response.json()}')
        return response.json()['result']['message_id']
    else:
        print(f'Failed to send message: {response.content}')
    resp = {'ok': True, 'result': {'message_id': 109, 'author_signature': 'SkyNet',
                                   'sender_chat': {'id': -1001863399780, 'title': 'BM: First rearding | Первое чтение',
                                                   'type': 'channel'},
                                   'chat': {'id': -1001863399780, 'title': 'BM: First rearding | Первое чтение',
                                            'type': 'channel'}, 'date': 1696287194, 'text': 'f'}}


def edit_telegram_message(chat_id, message_id, text):
    token = config.skynet_token.get_secret_value()
    url = f'https://api.telegram.org/bot{token}/editMessageText'
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML'  # Опционально: для форматирования текста
    }
    response = requests.post(url, data=data)
    if response.ok:
        # print(f'Message edited successfully: {response.json()}')
        return True
    else:
        print(f'Failed to edit message: {response.content}')
