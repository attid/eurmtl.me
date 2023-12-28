import json
import urllib.parse
import uuid
from quart import Blueprint, request, render_template, flash, jsonify, session, redirect, abort
from db.models import WebEditorMessages
from db.pool import db_pool
from utils.telegram_utils import send_telegram_message, edit_telegram_message, is_bot_admin, check_response, \
    is_user_admin, check_response_webapp, convert_html_to_telegram_format

blueprint = Blueprint('web_editor', __name__)


@blueprint.route('/WebEditor')
async def web_editor():
    # Получаем параметры запроса
    tg_web_app_start_param = request.args.get('tgWebAppStartParam')
    if tg_web_app_start_param:
        chat_id, message_id = tg_web_app_start_param.split('_')
        session['WebEditor'] = (chat_id, message_id)

        # Проверяем, является ли бот администратором в чате
        if not is_bot_admin(chat_id):
            return 'Бот не является администратором в данном чате', 403

        # Затем ищем в базе текст для этого сообщения
        with db_pool() as db_session:
            message_record = db_session.query(WebEditorMessages).filter(
                WebEditorMessages.chat_id == chat_id,
                WebEditorMessages.message_id == message_id
            ).first()

        if message_record:
            # Если текст найден, отображаем его в редакторе
            return await render_template('web_editor.html', message_text=message_record.message_text)
        else:
            # Если текста нет, пробуем отредактировать сообщение в Telegram
            random_hash = uuid.uuid4().hex
            reply_markup_json = await get_reply_markup(chat_id, message_id)

            # Вызываем функцию редактирования сообщения с клавиатурой
            edit_success = edit_telegram_message(int(f'-100{chat_id}'), message_id, f"Start edit {random_hash}",
                                                 reply_markup=reply_markup_json)
            if edit_success:
                return await render_template('web_editor.html', message_text='Your text here...')
            else:
                return 'Не удалось отредактировать сообщение', 500

    else:
        # Если параметр не передан, отображаем сообщение об ошибке
        return 'Параметры не найдены', 400


async def get_reply_markup(chat_id, message_id):
    edit_button_url = f'https://t.me/myMTLbot/WebEditor?startapp={chat_id}_{message_id}'
    # Формируем JSON для клавиатуры
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "Edit", "url": edit_button_url},
                {"text": "Edit", "url": edit_button_url}
            ]
        ]
    }
    reply_markup_json = json.dumps(reply_markup)
    return reply_markup_json


@blueprint.route('/WebEditorAction', methods=['POST'])
async def web_editor_action():
    data = await request.json
    chat_id, message_id = session.get('WebEditor', (0, 0))

    # Получаем initData
    init_data_str = data.get('initData')

    # Проверяем, что initData, chat_id, message_id не пустая и в правильном формате
    if not init_data_str or not chat_id or not message_id:
        return jsonify({'ok': False, 'error': 'initData отсутствует'}), 400

    # Проверяем права пользователя на редактирование
    if not user_has_edit_permissions(init_data_str, chat_id):
        return jsonify({'ok': False, 'error': 'Нет прав на редактирование'}), 403

    # Если есть текст, это запрос на сохранение
    if 'text' in data:
        with db_pool() as db_session:
            # Ищем соответствующую запись
            message_record = db_session.query(WebEditorMessages).filter(
                WebEditorMessages.chat_id == chat_id,
                WebEditorMessages.message_id == message_id
            ).first()

            # Если запись найдена, обновляем текст
            if message_record:
                message_record.message_text = data['text']
            else:
                # Если запись не найдена, создаем новую
                new_message_record = WebEditorMessages(
                    chat_id=chat_id,
                    message_id=message_id,
                    message_text=data['text']
                )
                db_session.add(new_message_record)

            # Сохраняем изменения в базе данных
            db_session.commit()

            # Выполняем редактирование сообщения в Telegram
            reply_markup_json = await get_reply_markup(chat_id, message_id)
            edit_success = edit_telegram_message(int(f'-100{chat_id}'), int(message_id),
                                                 convert_html_to_telegram_format(data['text']),
                                                 reply_markup=reply_markup_json)
            if edit_success:
                return jsonify({'ok': True}), 200
            else:
                return jsonify({'ok': False, 'error': 'Ошибка при редактировании сообщения'}), 500

    # Если текста нет, это просто запрос на проверку прав
    return jsonify({'ok': True}), 200


def user_has_edit_permissions(init_data_str, chat_id):
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

    # Проверяем, является ли пользователь администратором в чате
    return is_user_admin(chat_id, user_id)


if __name__ == '__main__':
    pass
