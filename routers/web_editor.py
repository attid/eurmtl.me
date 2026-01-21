import json
import urllib.parse
import uuid

import aiohttp
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from loguru import logger
from quart import Blueprint, request, render_template, jsonify, session, abort, current_app
from sulguk import SULGUK_PARSE_MODE

from other.config_reader import config
from db.sql_models import WebEditorMessages, WebEditorLogs
from other.telegram_tools import is_bot_admin, is_user_admin, check_response_webapp, skynet_bot, prepare_html_text
from other.quart_tools import get_ip

blueprint = Blueprint('web_editor', __name__)


@blueprint.route('/WebEditor')
async def web_editor():
    # https://eurmtl.me/WebEditor?tgWebAppStartParam=1971356387_245
    # Получаем параметры запроса
    tg_web_app_start_param = request.args.get('tgWebAppStartParam')
    if tg_web_app_start_param:
        chat_id, message_id = tg_web_app_start_param.split('_')
        chat_id = int(chat_id)
        session['WebEditor'] = (chat_id, message_id)

        # Проверяем, является ли бот администратором в чате
        if chat_id > 0 and not is_bot_admin(chat_id):
            return 'Бот не является администратором в данном чате', 403

        # Затем ищем в базе текст для этого сообщения
        async with current_app.db_pool() as db_session:
            if chat_id == 0:
                result = await db_session.execute(select(WebEditorMessages).filter(
                    WebEditorMessages.uuid == message_id
                ))
                message_record = result.scalars().first()
            else:
                result = await db_session.execute(select(WebEditorMessages).filter(
                    WebEditorMessages.chat_id == chat_id,
                    WebEditorMessages.message_id == message_id
                ))
                message_record = result.scalars().first()

        if message_record:
            # Если текст найден, отображаем его в редакторе
            return await render_template('tabler_web_editor.html', message_text=message_record.message_text)
        else:
            if chat_id == 0:
                abort(404)

            # Если текста нет, пробуем отредактировать сообщение в Telegram
            random_hash = uuid.uuid4().hex
            reply_markup = await get_reply_markup_aiogram(chat_id, int(message_id))

            # Вызываем функцию редактирования сообщения с клавиатурой
            # edit_success = edit_telegram_message(int(f'-100{chat_id}'), message_id, f"Start edit {random_hash}",
            #                                      reply_markup=reply_markup_json)
            try:
                await skynet_bot.edit_message_text(chat_id=int(f'-100{chat_id}'),
                                                   message_id=message_id,
                                                   text=f"Start edit {random_hash}",
                                                   reply_markup=reply_markup,
                                                   disable_web_page_preview=True)
                return await render_template('tabler_web_editor.html', message_text='Your text here...')
            except Exception as e:
                logger.error(e)
                return 'Не удалось отредактировать сообщение', 500

    else:
        # Если параметр не передан, отображаем сообщение об ошибке
        return 'Параметры не найдены', 400


# async def get_reply_markup(chat_id, message_id):
#     edit_button_url = f'https://t.me/myMTLbot/WebEditor?startapp={chat_id}_{message_id}'
#     # Формируем JSON для клавиатуры
#     reply_markup = {
#         "inline_keyboard": [
#             [
#                 {"text": "Edit", "url": edit_button_url},
#                 {"text": "Edit", "url": edit_button_url}
#             ]
#         ]
#     }
#     reply_markup_json = json.dumps(reply_markup)
#     return reply_markup_json

async def get_reply_markup_aiogram(chat_id: int, message_id: int) -> InlineKeyboardMarkup:
    edit_button_url = f'https://t.me/myMTLbot/WebEditor?startapp={chat_id}_{message_id}'

    # Create an InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()

    # Add two "Edit" buttons with the same URL
    builder.row(
        InlineKeyboardButton(text="Edit", url=edit_button_url),
        InlineKeyboardButton(text="Edit", url=edit_button_url)
    )

    # Build and return the InlineKeyboardMarkup
    return builder.as_markup()


@blueprint.route('/WebEditorAction', methods=['POST'])
async def web_editor_action():
    data = await request.json
    chat_id, message_id = session.get('WebEditor', (0, 0))
    chat_id = int(chat_id)

    # Получаем initData
    init_data_str = data.get('initData')

    # Проверяем, что initData, chat_id, message_id не пустая и в правильном формате
    if not init_data_str or not message_id:
        return jsonify({'ok': False, 'error': 'initData отсутствует'}), 400

    # Проверяем права пользователя на редактирование
    if chat_id > 0 and not user_has_edit_permissions(init_data_str, chat_id):
        return jsonify({'ok': False, 'error': 'Нет прав на редактирование'}), 403

    # Если есть текст, это запрос на сохранение
    if 'text' in data:
        async with current_app.db_pool() as db_session:
            if chat_id == 0:
                result = await db_session.execute(select(WebEditorMessages).filter(
                    WebEditorMessages.uuid == message_id
                ))
                message_record = result.scalars().first()
            else:
                result = await db_session.execute(select(WebEditorMessages).filter(
                    WebEditorMessages.chat_id == chat_id,
                    WebEditorMessages.message_id == message_id
                ))
                message_record = result.scalars().first()

            # Если запись найдена, обновляем текст
            if message_record:
                log_record = WebEditorLogs(
                    web_editor_message_id=message_record.id,
                    message_text=message_record.message_text
                )
                db_session.add(log_record)

                message_record.message_text = data['text']
            else:
                if chat_id == 0:
                    abort(404)
                new_message_record = WebEditorMessages(
                    chat_id=chat_id,
                    message_id=message_id,
                    message_text=data['text']
                )
                db_session.add(new_message_record)

            # Сохраняем изменения в базе данных
            await db_session.commit()
            if chat_id == 0:
                return jsonify({'ok': True}), 200
            # tg_inquiry = transform_html(data['text'])

            # Выполняем редактирование сообщения в Telegram
            reply_markup = await get_reply_markup_aiogram(chat_id, message_id)
            # edit_success = edit_telegram_message(int(f'-100{chat_id}'), int(message_id),
            #                                      tg_inquiry.text, entities=tg_inquiry.entities,
            #                                      reply_markup=reply_markup_json)
            try:
                await skynet_bot.edit_message_text(chat_id=int(f'-100{chat_id}'),
                                                   message_id=int(message_id),
                                                   text=prepare_html_text(data['text']),
                                                   reply_markup=reply_markup,
                                                   parse_mode=SULGUK_PARSE_MODE,
                                                   disable_web_page_preview=True
                                                   )

                return jsonify({'ok': True}), 200
            except Exception as e:
                logger.info(f"Error editing message: {e}")
                return jsonify({'ok': False, 'error': 'Ошибка при редактировании сообщения'}), 500

    # Если текста нет, это просто запрос на проверку прав
    return jsonify({'ok': True}), 200


def user_has_edit_permissions(init_data_str, chat_id, return_user=False):
    # Декодируем URL-кодированную строку
    decoded_str = urllib.parse.unquote(init_data_str)

    # Преобразуем строку запроса в словарь
    init_data = urllib.parse.parse_qs(decoded_str)

    # Преобразуем JSON-строку в словарь для ключа 'user'
    if 'user' in init_data:
        try:
            user_data = json.loads(init_data['user'][0])
            init_data['user'] = user_data
        except json.JSONDecodeError:
            print('Ошибка при декодировании JSON для пользователя')

    # Проверяем подлинность initData
    if not check_response_webapp(init_data_str):
        return False

    # Извлекаем user_id из initData
    user_id = init_data.get('user', {}).get('id', None)

    if return_user:
        return user_id
    else:
        # Проверяем, является ли пользователь администратором в чате
        return is_user_admin(chat_id, user_id)


async def check_response_captcha(token, v2):
    logger.info(v2)
    if v2:
        url = "https://smartcaptcha.yandexcloud.net/validate"
        params = {
            "secret": config.yandex_secret_key.get_secret_value(),
            "token": token,
            "ip": await get_ip()
        }

        async with aiohttp.ClientSession() as web_session:
            async with web_session.get(url, params=params) as response:
                result = await response.json()
                print(result)

        return result["status"] == "ok"

    else:
        url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
        params = {
            'secret': config.cloudflare_secret_key.get_secret_value(),
            'response': token
        }

        async with aiohttp.ClientSession() as web_session:
            async with web_session.post(url, data=params) as response:
                result = await response.json()

        return result.get('success')


@blueprint.route('/JoinCaptcha', methods=['GET', 'POST'])
async def join_captcha():
    # https://eurmtl.me/JoinCaptcha?tgWebAppStartParam=1971356387
    # https://core.telegram.org/bots/webapps#initializing-mini-apps

    if request.method == 'POST':
        data = await request.get_json()  # Changed from request.json to request.get_json()
        init_data_str = data.get('initData')
        chat_id = int(data.get('chatId'))
        token = data.get('token')
        v2 = data.get('v2') == 'true'

        user_id = user_has_edit_permissions(init_data_str, 0, True)
        logger.info(f'JoinCaptcha: {user_id} {token} {init_data_str} {v2}')

        if user_id and token and await check_response_captcha(token, v2=v2):
            await skynet_bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            return jsonify({'ok': True}), 200
        else:
            return jsonify({'ok': False, 'error': 'No user or token'}), 403

    else:
        # Получаем параметры запроса
        tg_web_app_start_param = request.args.get('tgWebAppStartParam')
        if tg_web_app_start_param and len(tg_web_app_start_param.split('_')) > 1:
            chat_id, captcha_type = tg_web_app_start_param.split('_')
            chat_id = int(chat_id)
            v2 = captcha_type == '2'
            return await render_template('join_captcha.html', chat_id=chat_id, v2=v2)
        else:
            return 'Параметры не найдены', 400


if __name__ == '__main__':
    pass
    # asyncio.run(test())
