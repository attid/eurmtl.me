import asyncio
import json
import requests
from datetime import datetime
from quart import Blueprint, request, make_response, render_template, flash, session, redirect, abort, jsonify
from stellar_sdk import Network, TransactionEnvelope
from stellar_sdk import Keypair
from stellar_sdk.exceptions import BadSignatureError
from stellar_sdk import DecoratedSignature
from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
from db.models import Transactions, Signers, Signatures, Alerts
from db.pool import db_pool
from routers.sign_tools import parse_xdr_for_signatures
from utils import decode_xdr_to_text, decode_xdr_to_base64, check_publish_state, check_response, check_user_weight, \
    send_telegram_message, is_valid_base64

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
    data = request.json
    xdr = data.get("xdr")

    if not xdr or not is_valid_base64(xdr):
        return jsonify({"error": "Invalid or missing base64 data"}), 400  # Bad Request

    result = await parse_xdr_for_signatures(xdr)

    if result["SUCCESS"]:
        return jsonify(result), 200  # OK
    else:
        return jsonify(result), 404  # Not Found

if __name__ == '__main__':
    print(asyncio.run(remote_need_sign('GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI')))