import asyncio
import json
import uuid

from quart import Blueprint, request, jsonify, abort

from config.config_reader import config
from db.mongo import get_all_assets
from db.sql_models import Transactions, Signers, Signatures, WebEditorMessages, MMWBTransactions
from db.sql_pool import db_pool
from routers.sign_tools import parse_xdr_for_signatures
from utils.stellar_utils import decode_xdr_to_text, is_valid_base64, add_transaction

blueprint = Blueprint('remote', __name__)


@blueprint.route('/remote/need_sign/<public_key>', methods=('GET',))
async def remote_need_sign(public_key):
    with db_pool() as db_session:
        # Получаем подписанта по публичному ключу
        signer = db_session.query(Signers).filter(Signers.public_key == public_key).first()
        if not signer:
            return jsonify({'error': 'Signer not found'}), 404

        # Получаем транзакции, требующие подписи этого подписанта
        transactions = db_session.query(Transactions).filter(
            Transactions.json.contains(public_key),
            Transactions.state == 0
        ).order_by(Transactions.add_dt.desc()).all()

        # Фильтруем транзакции, убирая те, для которых подпись уже существует
        result = []
        for transaction in transactions:
            signature_exists = db_session.query(Signatures).filter(
                Signatures.transaction_hash == transaction.hash,
                Signatures.signer_id == signer.id
            ).first() is not None

            if not signature_exists:
                result.append({
                    'hash': transaction.hash,
                    'body': transaction.body,
                    'add_dt': transaction.add_dt.isoformat(),
                    'description': transaction.description
                })

        return jsonify(result)


@blueprint.route('/remote/update_signature', methods=('POST',))
async def remote_update_signature():
    data = await request.json
    xdr = data.get("xdr")

    if not xdr or not is_valid_base64(xdr):
        return jsonify({"error": "Invalid or missing base64 data"}), 400  # Bad Request

    result = await parse_xdr_for_signatures(xdr)

    if result["SUCCESS"]:
        return jsonify(result), 200  # OK
    else:
        return jsonify(result), 404  # Not Found


@blueprint.route('/remote/decode', methods=('GET', 'POST'))
async def remote_decode_xdr():
    data = await request.json
    xdr = data.get("xdr")

    if not xdr or not is_valid_base64(xdr):
        return jsonify({"error": "Invalid or missing base64 data"}), 400  # Bad Request

    encoded_xdr = await decode_xdr_to_text(xdr)

    encoded_xdr = ('<br>'.join(encoded_xdr)).replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')

    return jsonify({"text": encoded_xdr}), 200


@blueprint.route('/remote/get_xdr/<tr_hash>')
async def remote_get_xdr(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        abort(404)

    with db_pool() as db_session:
        if len(tr_hash) == 64:
            transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
        else:
            transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()

    if transaction is None:
        return 'Transaction not exist =('

    return jsonify({"xdr": transaction.body}), 200


@blueprint.route('/remote/get_new_pin_id')
async def remote_get_new_pin_id():
    api_key = request.headers.get('Authorization')
    if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
        return jsonify({"message": "Unauthorized"}), 401

    message_uuid = uuid.uuid4().hex

    with db_pool() as db_session:
        msg = WebEditorMessages(uuid=message_uuid, message_text='New Text')
        db_session.add(msg)
        db_session.commit()

    return jsonify({"uuid": message_uuid}), 200


@blueprint.route('/remote/good_assets', methods=['GET'])
async def remote_good_assets():
    # Получаем активы, у которых need_eurmtl равно True
    assets = await get_all_assets(True)

    # Переструктурируем данные, группируя активы по issuer (это аналогично account)
    account_assets = {}
    for asset in assets:
        issuer = asset.issuer
        if issuer not in account_assets:
            account_assets[issuer] = []
        account_assets[issuer].append(asset)

    # Формируем ответ в виде JSON
    accounts = [{
        "account": issuer,
        "assets": [{"asset": asset.name} for asset in assets]
    } for issuer, assets in account_assets.items()]

    return jsonify({"accounts": accounts})


@blueprint.route('/remote/get_mmwb_transaction', methods=['POST'])
async def remote_get_mmwb_transaction():
    api_key = request.headers.get('Authorization')
    if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
        return jsonify({"message": "Unauthorized"}), 401

    data = await request.json
    user_id = data.get('user_id')
    message_uuid = data.get('uuid')

    with db_pool() as db_session:
        message_record = db_session.query(MMWBTransactions).filter(
            MMWBTransactions.uuid == message_uuid,
            MMWBTransactions.tg_id == user_id
        ).first()

    if message_record is None:
        return jsonify({"message": "Message not found"}), 404

    return jsonify(json.loads(message_record.json)), 200


@blueprint.route('/remote/add_transaction', methods=['POST'])
async def remote_add_transaction():
    api_key = request.headers.get('Authorization')
    if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
        return jsonify({"message": "Unauthorized"}), 401

    data = await request.json
    tx_body = data.get('tx_body')
    tx_description = data.get('tx_description')

    if not tx_body or not tx_description:
        return jsonify({"message": "Missing tx_body or tx_description"}), 400

    if len(tx_description) < 5:
        return jsonify({"message": "Description too short"}), 400

    success, result = await add_transaction(tx_body, tx_description)
    if success:
        return jsonify({"message": "Transaction added successfully", "hash": result}), 201
    else:
        return jsonify({"message": result}), 400


if __name__ == '__main__':
    print(asyncio.run(remote_need_sign('GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI')))
