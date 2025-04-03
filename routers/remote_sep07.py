import asyncio
import json
import uuid
import hashlib
import base64

from stellar_sdk.sep import stellar_uri
from quart import Blueprint, request, jsonify, abort

from other.config_reader import config
from db.sql_models import Transactions, Signers, Signatures, WebEditorMessages, MMWBTransactions
from db.sql_pool import db_pool
from other.grist_tools import grist_manager, MTLGrist
from routers.sign_tools import parse_xdr_for_signatures
from other.stellar_tools import decode_xdr_to_text, is_valid_base64, add_transaction
from other.web_tools import cors_jsonify

blueprint = Blueprint('sep07', __name__, url_prefix='/remote/sep07')

@blueprint.route('', methods=('POST', 'OPTIONS'))
async def remote_sep07():
    """
    Обработчик для SEP-0007 колбека.
    
    Принимает параметры:
    - xdr: XDR транзакции для подписи
    
    Возвращает:
    - JSON с полями status и hash при успешной обработке
    - Код 200 при успехе, не 200 при ошибке
    States
    failed = "failed",
    pending = "pending",
    ready = "ready",
    submitted = "submitted"
    """
    # Обработка OPTIONS запроса для CORS preflight
    if request.method == 'OPTIONS':
        return cors_jsonify({})
    
    form_data = await request.form
    xdr = form_data.get("xdr")
    
    if not xdr or not is_valid_base64(xdr):
        return cors_jsonify({
            "status": "failed",
            "hash": "",
            "error": {
                "message": "Invalid or missing base64 data",
                "details": None
            }
        }, 400)  # Bad Request
    
    # Обрабатываем XDR и получаем результат
    result = await parse_xdr_for_signatures(xdr)
    
    # Формируем ответ на основе результата parse_xdr_for_signatures
    if result["SUCCESS"]:
        return cors_jsonify({
            "status": "pending",  # Если SUCCESS=True
            "hash": result.get("hash", "")  # Получаем хеш из результата
        })  # OK (200 по умолчанию)
    else:
        return cors_jsonify({
            "status": "failed",
            "hash": result.get("hash", ""),
            "error": {
                "message": "; ".join(result.get("MESSAGES", [])),
                "details": None
            }
        }, 404)  # Not Found


@blueprint.route('/add', methods=['POST', 'OPTIONS'])
@blueprint.route('/add/', methods=['POST', 'OPTIONS'])
async def remote_add_uri():
    """
    Handles saving a Stellar URI and generating a URL for it.
    
    Accepts:
    - URI: A Stellar URI string
    
    Returns:
    - JSON with SUCCESS flag and generated URL
    - 200 status code on success, error code otherwise
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return cors_jsonify({})
    
    data = await request.json
    uri = data.get('uri')

    if not uri:
        return cors_jsonify({"SUCCESS": False, "message": "Missing URI"}), 400

    try:
        # Parse the URI to verify it's valid
        transaction_uri = stellar_uri.parse(uri)
        
        # Check that this is an XDR URI (not a payment)
        if not isinstance(transaction_uri, stellar_uri.TransactionStellarUri):
            return cors_jsonify({
                "SUCCESS": False,
                "message": "Invalid URI type. Expected transaction URI."
            }), 400
        
        # Get the transaction XDR
        xdr = transaction_uri.xdr
        
        # Generate a key using SHA1 of the transaction hash, encoded as base64url
        hash_obj = hashlib.sha1(xdr.encode('utf-8'))
        hash_digest = hash_obj.digest()
        key = base64.urlsafe_b64encode(hash_digest).decode('utf-8')
        
        # Ensure the key is not longer than 32 characters
        if len(key) > 32:
            key = key[:32]
        
        # Save the URI in the database
        with db_pool() as db_session:
            transaction = MMWBTransactions(
                uuid=key,
                json=json.dumps({'uri': uri})
            )
            db_session.add(transaction)
            db_session.commit()
        
        # Generate the URL
        url = f"https://t.me/MyMTLWalletBot?start=uri_{key}"
        
        return cors_jsonify({
            "SUCCESS": True,
            "url": url
        }), 200
    except Exception as e:
        return cors_jsonify({
            "SUCCESS": False,
            "message": f"Error processing URI: {str(e)}"
        }), 500


@blueprint.route('/get/<uuid_key>', methods=['GET', 'OPTIONS'])
async def get(uuid_key):
    """
    Retrieves a saved URI by its UUID key.
    
    Parameters:
    - uuid_key: The UUID key of the saved URI
    
    Returns:
    - JSON with the URI if found
    - 404 if not found
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return cors_jsonify({})
    
    try:
        with db_pool() as db_session:
            transaction = db_session.query(MMWBTransactions).filter(
                MMWBTransactions.uuid == uuid_key
            ).first()
            
            if not transaction:
                return cors_jsonify({
                    "SUCCESS": False,
                    "message": "URI not found"
                }), 404
            
            # Parse the JSON to get the URI
            data = json.loads(transaction.json)
            uri = data.get('uri')
            
            if not uri:
                return cors_jsonify({
                    "SUCCESS": False,
                    "message": "URI data is corrupted"
                }), 500
            
            return cors_jsonify({
                "SUCCESS": True,
                "uri": uri
            }), 200
    except Exception as e:
        return cors_jsonify({
            "SUCCESS": False,
            "message": f"Error retrieving URI: {str(e)}"
        }), 500


if __name__ == '__main__':
    print(asyncio.run(print('GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI')))
