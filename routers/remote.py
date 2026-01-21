import asyncio
import json
import uuid

from sqlalchemy import select
from quart import Blueprint, request, jsonify, abort, current_app

from other.config_reader import config
from db.sql_models import Transactions, Signers, Signatures, WebEditorMessages, MMWBTransactions
from other.grist_tools import grist_manager, MTLGrist
from routers.sign_tools import parse_xdr_for_signatures
from services.xdr_parser import decode_xdr_to_text, is_valid_base64
from services.stellar_client import add_transaction
from other.web_tools import cors_jsonify
from routers.remote_sep07_auth import blueprint as sep07_blueprint_auth
from routers.remote_sep07 import blueprint as sep07_blueprint
from infrastructure.repositories.transaction_repository import TransactionRepository

blueprint = Blueprint('remote', __name__)
blueprint.register_blueprint(sep07_blueprint)
blueprint.register_blueprint(sep07_blueprint_auth)


@blueprint.route('/remote/need_sign/<public_key>', methods=('GET',))
async def remote_need_sign(public_key):
    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        
        # Получаем подписанта по публичному ключу
        signer = await repo.get_signer_by_public_key(public_key)
        if not signer:
            return jsonify({'error': 'Signer not found'}), 404

        # Получаем транзакции, требующие подписи этого подписанта
        transactions = await repo.get_pending_for_signer(signer)

        # Формируем ответ
        result_list = []
        for transaction in transactions:
            result_list.append({
                'hash': transaction.hash,
                'body': transaction.body,
                'add_dt': transaction.add_dt.isoformat(),
                'description': transaction.description
            })

        return jsonify(result_list)


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

    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        if len(tr_hash) == 64:
            transaction = await repo.get_by_hash(tr_hash)
        else:
            transaction = await repo.get_by_uuid(tr_hash)

    if transaction is None:
        return 'Transaction not exist =('

    return jsonify({"xdr": transaction.body}), 200


@blueprint.route('/remote/get_new_pin_id')
async def remote_get_new_pin_id():
    api_key = request.headers.get('Authorization')
    if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
        return jsonify({"message": "Unauthorized"}), 401

    message_uuid = uuid.uuid4().hex

    async with current_app.db_pool() as db_session:
        msg = WebEditorMessages(uuid=message_uuid, message_text='New Text')
        db_session.add(msg)
        await db_session.commit()

    return jsonify({"uuid": message_uuid}), 200


@blueprint.route('/remote/good_assets', methods=['GET'])
async def remote_good_assets():
    # Получаем активы, xz
    assets = await grist_manager.load_table_data(
        MTLGrist.EURMTL_assets,
        # filter_dict={"need_dropdown": [True]}
    )

    # Переструктурируем данные, группируя активы по issuer (это аналогично account)
    account_assets = {}
    for asset in assets:
        issuer = asset["issuer"]
        if issuer not in account_assets:
            account_assets[issuer] = []
        account_assets[issuer].append(asset)

    # Формируем ответ в виде JSON
    accounts = [{
        "account": issuer,
        "assets": [{"asset": asset["name"]} for asset in assets]
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

    async with current_app.db_pool() as db_session:
        result = await db_session.execute(select(MMWBTransactions).filter(
            MMWBTransactions.uuid == message_uuid,
            MMWBTransactions.tg_id == user_id
        ))
        message_record = result.scalars().first()

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
