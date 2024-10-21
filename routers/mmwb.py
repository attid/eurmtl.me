import json

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger
from quart import Blueprint, request, render_template, jsonify

from config.config_reader import config
from db.sql_models import MMWBTransactions
from db.sql_pool import db_pool
from utils.stellar_utils import get_account, decode_data_value, stellar_manage_data
from utils.telegram_utils import check_response_webapp, mmwb_bot

blueprint = Blueprint('mmwb', __name__)


@blueprint.route('/ManageData')
async def manage_data():
    # https://eurmtl.me/ManageData?user_id=84131737&message_id=4656&account_id=GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI
    # Получаем параметры запроса
    account_id = request.args.get('account_id')

    if account_id:
        cash = {}
        account = get_account(account_id, cash)
        data = account.get('data', {})

        for key in data.keys():
            try:
                data[key] = decode_data_value(data[key])
            except:
                data[key] = 'error decode =('

        return await render_template('mmwb_manage_data.html', data=data)
    else:
        # Если параметр не передан, отображаем сообщение об ошибке
        return 'Параметры не найдены', 400


async def get_md_reply_markup(uuid_callback_data: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Decode", callback_data=f"MDCallbackData:{uuid_callback_data}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@blueprint.route('/ManageDataAction', methods=['POST'])
async def manage_data_action():
    data = await request.json
    user_id = data.get('user_id')
    message_id = data.get('message_id')
    account_id = data.get('account_id')
    key = data.get('key')
    value = data.get('value')

    # Получаем initData
    init_data_str = data.get('initData')

    if not init_data_str or not message_id or not user_id:
        return jsonify({'ok': False, 'error': 'initData отсутствует'}), 400

    if not check_response_webapp(init_data_str, config.mmwb_token):
        return jsonify({'ok': False, 'error': 'Нет прав на редактирование'}), 403

    with db_pool() as db_session:
        xdr = await stellar_manage_data(account_id, key, value)
        record = MMWBTransactions(tg_id=user_id, json=json.dumps({'xdr': xdr}))
        db_session.add(record)
        db_session.commit()

        # Выполняем редактирование сообщения в Telegram
        reply_markup = await get_md_reply_markup(record.uuid)
        try:
            await mmwb_bot.edit_message_text(chat_id=int(user_id),
                                             message_id=int(message_id),
                                             text='Press <b>Decode</b> to continue',
                                             reply_markup=reply_markup,
                                             parse_mode='HTML')
            return jsonify({'ok': True}), 200
        except Exception as e:
            logger.info(f'Ошибка при редактировании сообщения: {e}')
            return jsonify({'ok': False, 'error': 'Ошибка при редактировании сообщения'}), 500


if __name__ == '__main__':
    pass
