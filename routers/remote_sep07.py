import secrets
from datetime import datetime, timedelta
from urllib.parse import quote
from loguru import logger

from quart import Blueprint, jsonify, request, render_template

from other.config_reader import config
from other.qr_tools import create_beautiful_code
from other.stellar_tools import create_sep7_auth_transaction, process_xdr_transaction, is_valid_base64
from other.web_tools import cors_jsonify

blueprint = Blueprint('sep07', __name__, url_prefix='/remote/sep07/auth')

# Хранилище nonce
nonce_store = {}
MAX_NONCE_STORE_SIZE = 1000
NONCE_LIFETIME = timedelta(minutes=5)


def cleanup_nonce_store():
    """Очистка устаревших nonce"""
    now = datetime.now()
    expired = [n for n, t in nonce_store.items() if now - t['created'] > NONCE_LIFETIME]
    for n in expired:
        del nonce_store[n]

    # Если хранилище переполнено, удаляем самые старые записи
    if len(nonce_store) > MAX_NONCE_STORE_SIZE:
        oldest = sorted(nonce_store.items(), key=lambda x: x[1]['created'])[:len(nonce_store) - MAX_NONCE_STORE_SIZE]
        for n, _ in oldest:
            del nonce_store[n]


@blueprint.route("/test")
@blueprint.route("/test/")
async def auth_test():
    return await render_template('sep07test.html')


@blueprint.route('/init', methods=['POST', 'OPTIONS'])
async def auth_init():
    if request.method == 'OPTIONS':
        return cors_jsonify({})  # пустой ответ, но с CORS-заголовками
    # Очищаем хранилище от старых nonce
    cleanup_nonce_store()

    data = await request.json
    domain = data.get('domain')
    nonce = data.get('nonce')
    salt = data.get('salt', secrets.token_hex(4))

    if not domain or not nonce:
        return jsonify({'error': 'domain and nonce are required'}), 400

    # Проверяем длину nonce и salt
    if len(nonce) > 64:
        return jsonify({'error': 'nonce length should not exceed 64 characters'}), 400

    if len(salt) > 64:
        return jsonify({'error': 'salt length should not exceed 64 characters'}), 400

    # Сохраняем nonce в хранилище
    nonce_store[nonce] = {
        "created": datetime.now(),
        "domain": domain,
        "salt": str(salt),  # Преобразуем в строку для корректной сериализации
        "tx_info": None
    }

    callback_url = f'https://{config.domain}/remote/sep07/auth/callback'

    # Generate transaction URI
    uri = await create_sep7_auth_transaction(domain, nonce, callback=callback_url)

    # Generate QR code
    qr_uuid = secrets.token_hex(8)
    qr_path = f'/static/qr/{qr_uuid}.png'
    create_beautiful_code(file_name=qr_path, logo_text=domain, qr_text=uri)

    return cors_jsonify({
        'qr_path': qr_path,
        'uri': uri,
        'status_url': f'/remote/sep07/auth/status/{nonce}/{salt}'
    })


@blueprint.route('/status/<nonce>/<salt>', methods=['GET', 'OPTIONS'])
async def auth_status(nonce, salt):
    if request.method == 'OPTIONS':
        return cors_jsonify({})  # пустой ответ, но с CORS-заголовками
    # Ищем nonce в хранилище
    if nonce not in nonce_store:
        return jsonify({"error": "nonce not found"}), 400

    # Проверяем соль
    nonce_data = nonce_store[nonce]
    if nonce_data["salt"] != salt:
        return jsonify({"error": "nonce not found"}), 400

    # Если есть информация о транзакции
    if nonce_data["tx_info"]:
        del nonce_store[nonce]
        return cors_jsonify({
            "authenticated": True,
            "nonce": nonce,
            "hash": nonce_data["tx_info"]["hash"],
            "client_address": nonce_data["tx_info"]["client_address"],
            "timestamp": nonce_data["tx_info"]["timestamp"],
            "domain": nonce_data["tx_info"]["domain"]
        })

    return cors_jsonify({
        "authenticated": False,
        "nonce": nonce
    })


@blueprint.route('/callback', methods=['POST', 'OPTIONS'])
async def auth_callback():
    # Обработка OPTIONS запроса для CORS preflight
    if request.method == 'OPTIONS':
        return cors_jsonify({})

    form_data = await request.form
    logger.info(f"Callback request received. Form keys: {form_data.keys()}")

    if "xdr" not in form_data:
        logger.warning("No xdr in callback request")
        return jsonify({"error": "Нет данных"}), 400

    signed_xdr = form_data["xdr"]
    logger.debug(f"Processing signed xdr: {signed_xdr[:50]}...")
    logger.debug(signed_xdr)

    # Проверяем, что полученные данные - валидный XDR
    if not is_valid_base64(signed_xdr):
        logger.warning(f"Invalid XDR format: {signed_xdr[:50]}...")
        return jsonify({"error": "Неверный формат XDR"}), 400

    try:
        logger.info("Starting transaction processing")

        # Обрабатываем XDR
        tx_info = await process_xdr_transaction(signed_xdr)

        nonce_value = tx_info["nonce"]
        logger.debug(f"Checking nonce: {nonce_value}")

        if nonce_value not in nonce_store:
            logger.warning(f"Invalid nonce: {nonce_value}")
            return jsonify({"error": "Неверный nonce"}), 400

        # Проверяем время жизни nonce
        nonce_age = datetime.now() - nonce_store[nonce_value]["created"]
        logger.debug(f"Nonce age: {nonce_age}")
        if nonce_age > NONCE_LIFETIME:
            logger.warning(f"Expired nonce: {nonce_value}, age: {nonce_age}")
            del nonce_store[nonce_value]
            return jsonify({"error": "Истек срок действия nonce"}), 400

        # Сохраняем информацию о транзакции
        nonce_store[nonce_value]["tx_info"] = {
            "hash": tx_info["hash"],
            "client_address": tx_info["client_address"],
            "timestamp": tx_info["timestamp"],
            "domain": tx_info["domain"]
        }
        logger.info(f"Nonce {nonce_value} validated and tx info saved")

        return cors_jsonify({
            "status": "pending",
            "hash": tx_info["hash"]
        })
    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 400
