from datetime import datetime
from quart import Blueprint, jsonify, render_template, request

from other.config_reader import config
from other.grist_tools import grist_manager, MTLGrist
from loguru import logger

blueprint = Blueprint('grist', __name__)


# wijets

@blueprint.route('/grist/tg_info.html', methods=('GET',))
async def grist_tg_info():  #
    return await render_template('grist_tg_info.html')


# js points


#from db.mongo import get_all_chats_by_user


@blueprint.route('/grist/groups/<user_id>', methods=('GET',))
async def grist_tg_info_groups(user_id):
    # Получаем ключ из заголовка
    auth_key = request.headers.get('X-Auth-Key')

    # Проверяем ключ с логированием
    key_check = await check_grist_key(
        auth_key,
        log_info=f'grist_tg_info_groups {user_id}'
    )
    if key_check['status'] != 'success':
        return jsonify(key_check), 403

    # Получаем данные о чатах пользователя
    try:
        user_id_int = int(user_id)
        chats = [] # await get_all_chats_by_user(user_id_int)

        # Подготавливаем данные для шаблона
        chat_data = []
        for chat in chats:
            user_data = chat.users.get(str(user_id_int))
            if not user_data:
                continue

            chat_data.append({
                'title': chat.title or f"ID: {chat.chat_id}",
                'joined': user_data.created_at.strftime('%Y-%m-%d %H:%M') if user_data.created_at else '-',
                'left': user_data.left_at.strftime('%Y-%m-%d %H:%M') if user_data.left_at else '-'
            })

        return await render_template(
            'grist_tg_groups.html',
            chats=chat_data
        )

    except Exception as e:
        logger.error(f"Error getting chat info: {e}")
        return jsonify({
            "status": "error",
            "message": "Ошибка при получении данных о чатах"
        }), 500


async def _process_grist_key(key: str, record: dict):
    """Обрабатывает запись из Grist в зависимости от ключа."""
    rec_id = record.get('id')
    if not rec_id:
        logger.warning("Grist webhook: не найден id в data для обновления")
        return

    task_function = None
    if key == 'TEST':
        # Для 'TEST' нет дополнительной задачи, просто обновление
        task_function = None
    elif key == 'MTL':
        from other.grist_tools import update_mtl_shareholders_balance
        task_function = update_mtl_shareholders_balance
    else:
        logger.warning(f"Grist webhook: неизвестный ключ '{key}'")
        return

    try:
        # Выполняем основную задачу, если она есть
        if task_function:
            await task_function()

        # Обновляем запись в AdminPanel
        from other.grist_tools import grist_manager, MTLGrist
        from datetime import datetime, timezone
        update_data = {
            "records": [{
                "id": rec_id,
                "fields": {
                    "DATE": datetime.now(timezone.utc).isoformat(),
                    "UPDATE": False
                }
            }]
        }
        await grist_manager.patch_data(MTLGrist.MTL_admin_panel, update_data)
        logger.info(f"Grist webhook: запись id={rec_id} для ключа '{key}' успешно обработана.")

    except Exception as e:
        logger.error(f"Grist webhook: ошибка при обработке ключа '{key}' для id={rec_id}: {e}")


async def check_grist_key(key: str, log_info: str = None) -> dict:
    """Проверка ключа доступа к Grist с использованием кеша"""
    if not key:
        return {"status": "error", "message": "Необходимо указать ключ"}

    try:
        # Ищем запись в кеше по индексу
        from other.grist_cache import grist_cache
        record = grist_cache.find_by_index('GRIST_access', key)

        if not record:
            return {
                "status": "error",
                "message": "Неверный ключ"
            }

        # Логируем запрос если указана информация для логирования
        if log_info:
            await grist_manager.post_data(
                MTLGrist.GRIST_use_log,
                json_data={
                    "records": [{
                        "fields": {
                            "user_id": record.get('user_id'),
                            "dt_use": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "info": log_info
                        }
                    }]
                }
            )

        return {
            "status": "success",
            "message": "Ключ действителен",
            "data": {
                "dt_update": record.get('dt_update'),
                "user_id": record.get('user_id')
            }
        }

    except Exception as e:
        logger.error(f"Grist key check error: {e}")
        return {
            "status": "error",
            "message": "Ошибка при проверке ключа"
        }


@blueprint.route('/grist/menu', methods=('GET',))
async def grist_tg_info_menu():
    # Получаем ключ из заголовка
    auth_key = request.headers.get('X-Auth-Key')

    # Проверяем ключ
    key_check = await check_grist_key(auth_key)
    if key_check['status'] != 'success':
        return jsonify(key_check), 403

    menu_data = {
        "buttons": [
            {
                "title": "Группы",
                "endpoint": "https://eurmtl.me/grist/groups/$user_id$"
            },
            {
                "title": "Связь со скаей",
                "endpoint": "https://eurmtl.me/grist/sky_test/$user_id$"
            }
        ]
    }
    return jsonify(menu_data)


@blueprint.route('/grist/sky_test/<user_id>', methods=('GET',))
async def grist_sky_test(user_id: str):
    # Проверяем ключ доступа с логированием
    auth_key = request.headers.get('X-Auth-Key')
    key_check = await check_grist_key(
        auth_key,
        log_info=f'grist_sky_test {user_id}'
    )
    if key_check['status'] != 'success':
        return jsonify(key_check), 403

    # Проверяем наличие user_id
    if not user_id:
        return jsonify({
            "status": "error",
            "message": "Необходимо указать user_id"
        }), 400

    try:
        # Преобразуем user_id в int
        user_id_int = int(user_id)

        # Получаем skynet_bot из telegram_tools
        from other.telegram_tools import skynet_bot

        # Проверяем подписку
        try:
            chat = await skynet_bot.get_chat(user_id_int)
            return """
                <div class="alert alert-success" role="alert">
                    <h4 class="alert-heading">Успешно!</h4>
                    <p>Пользователь подписан на SkyNet</p>
                </div>
            """
        except Exception as e:
            return """
                <div class="alert alert-danger" role="alert">
                    <h4 class="alert-heading">Ошибка!</h4>
                    <p>Пользователь не подписан на SkyNet</p>
                </div>
            """
    except ValueError:
        return jsonify({
            "status": "error",
            "message": "Некорректный формат user_id"
        }), 400
    except Exception as e:
        logger.error(f"SkyNet test error: {e}")
        return jsonify({
            "status": "error",
            "message": "Ошибка при проверке подписки"
        }), 500


@blueprint.route('/grist/webhook/<table_name>', methods=('GET','POST'))
async def grist_webhook_table(table_name: str):
    """Вебхук для обновления кеша конкретной таблицы"""
    logger.info(f"Grist webhook для таблицы {table_name}")
    
    # Проверка ключа безопасности
    auth_header = request.headers.get('X-Auth-Key') or request.headers.get('Authorization')
    auth_key = None
    if auth_header:
        if auth_header.startswith('Bearer '):
            auth_key = auth_header[7:].strip()
        else:
            auth_key = auth_header.strip()

    try:
        grist_income = config.grist_income
    except Exception as e:
        logger.error(f"Grist webhook: не удалось получить grist_income: {e}")
        grist_income = None

    if not auth_key or not grist_income or auth_key != grist_income:
        logger.warning('Grist webhook: неверный ключ')
        return jsonify({"status": "accepted"})

    # Обновляем кеш для таблицы
    try:
        from other.grist_cache import grist_cache
        await grist_cache.update_cache_by_webhook(table_name)
    except Exception as e:
        logger.error(f"Ошибка обновления кеша для таблицы {table_name}: {e}")
    
    return jsonify({"status": "accepted"})


@blueprint.route('/grist/webhook', methods=('GET','POST'))
async def grist_webhook():
    """Старый вебхук для обратной совместимости"""
    logger.info(f"Grist webhook (legacy) headers: {request.headers}")
    data = await request.json
    logger.info(f"Grist webhook (legacy): {data}")

    # Получаем ключ из заголовка X-Auth-Key или Authorization, поддерживаем формат 'Bearer <ключ>'
    auth_header = request.headers.get('X-Auth-Key') or request.headers.get('Authorization')
    auth_key = None
    if auth_header:
        if auth_header.startswith('Bearer '):
            auth_key = auth_header[7:].strip()
        else:
            auth_key = auth_header.strip()

    # Проверка ключа
    try:
        grist_income = config.grist_income
    except Exception as e:
        logger.error(f"Grist webhook: не удалось получить grist_income: {e}")
        grist_income = None

    if not auth_key or not grist_income or auth_key != grist_income:
        logger.warning('Grist webhook: неверный ключ')
        # Всегда отвечаем 200 OK, чтобы Grist не повторял запросы
        return jsonify({"status": "accepted"})

    # Проверяем что пришёл список
    if not isinstance(data, list) or not data:
        logger.warning('Grist webhook: bad request, data is not list or empty')
        return jsonify({"status": "accepted"})

    record = data[0]
    # Проверка UPDATE и KEY
    if record.get('UPDATE') and record.get('KEY'):
        await _process_grist_key(record.get('KEY'), record)
    else:
        logger.info('Grist webhook: UPDATE is not True or KEY is missing, skipping')

    # Всегда отвечаем 200 OK
    return jsonify({"status": "accepted"})


if __name__ == '__main__':
    pass
    # print(asyncio.run(remote_need_sign('GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI')))
