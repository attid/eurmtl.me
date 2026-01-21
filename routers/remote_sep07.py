import asyncio
import json
import uuid
import hashlib
import base64
from loguru import logger

from stellar_sdk.sep import stellar_uri
from stellar_sdk import Network, TransactionEnvelope, TransactionBuilder, Keypair
from sqlalchemy import select
from quart import Blueprint, request, jsonify, abort, render_template, current_app
import traceback
from urllib.parse import urlparse, parse_qs, unquote

from other.config_reader import config
from db.sql_models import Transactions, Signers, Signatures, WebEditorMessages, MMWBTransactions
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
        return cors_jsonify({"SUCCESS": False, "message": "Missing URI"}, 400)

    try:
        logger.info(f"Processing URI: {uri[:100]}...")

        # Try to parse URI as-is first
        try:
            transaction_uri = stellar_uri.TransactionStellarUri.from_uri(uri,
                                                                         network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            logger.debug(f"Successfully parsed URI without decoding: {transaction_uri}")
        except Exception as e:
            logger.warning(f"Failed to parse URI directly: {str(e)}")
            # If parsing fails, try URL-decoding the URI first
            from urllib.parse import unquote
            decoded_uri = unquote(uri)
            logger.debug(f"Trying decoded URI: {decoded_uri[:100]}...")
            try:
                transaction_uri = stellar_uri.TransactionStellarUri.from_uri(decoded_uri,
                                                                             network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
                logger.debug(f"Successfully parsed URI after decoding: {transaction_uri}")
            except Exception as e:
                logger.error(f"Failed to parse URI after decoding: {str(e)}")
                return cors_jsonify({
                    "SUCCESS": False,
                    "message": f"Invalid URI: {str(e)}"
                }, 400)

        # Check that we have a valid transaction URI
        if not isinstance(transaction_uri, stellar_uri.TransactionStellarUri):
            return cors_jsonify({
                "SUCCESS": False,
                "message": "Invalid URI type. Expected transaction URI."
            }, 400)

        # Get the transaction XDR from envelope
        try:
            xdr = transaction_uri.transaction_envelope.to_xdr()
            logger.debug(f"Extracted XDR: {xdr[:50]}...")
        except Exception as e:
            logger.error(f"Failed to get XDR from URI: {str(e)}")
            return cors_jsonify({
                "SUCCESS": False,
                "message": f"Failed to extract transaction from URI: {str(e)}"
            }, 400)

        # Generate a key using SHA1 of the transaction hash, encoded as base64url
        hash_obj = hashlib.sha1(xdr.encode('utf-8'))
        hash_digest = hash_obj.digest()
        key = base64.urlsafe_b64encode(hash_digest).decode('utf-8').rstrip('=')

        # Ensure the key is not longer than 32 characters
        if len(key) > 32:
            key = key[:32]

        logger.debug(f"Generated key: {key}")

        # Save the URI in the database without blocking event loop
        try:
            status = "saved"
            async with current_app.db_pool() as db_session:
                result = await db_session.execute(select(MMWBTransactions).filter_by(uuid=key))
                existing_transaction = result.scalars().first()

                if existing_transaction:
                    existing_data = json.loads(existing_transaction.json)
                    if existing_data.get('uri') == uri:
                        status = "exists_same"
                    else:
                        status = "exists_different"
                else:
                    transaction = MMWBTransactions(
                        uuid=key,
                        json=json.dumps({'uri': uri})
                    )
                    db_session.add(transaction)
                    await db_session.commit()
                    status = "saved"
            if status == "exists_same":
                logger.info("Transaction already exists in database")
                url = f"https://t.me/MyMTLWalletBot?start=uri_{key}"
                return cors_jsonify({
                    "SUCCESS": True,
                    "message": "Transaction already exists in database",
                    "url": url
                }, 200)
            if status == "exists_different":
                logger.error("Transaction with same UUID but different URI already exists")
                return cors_jsonify({
                    "SUCCESS": False,
                    "message": "Transaction with same UUID but different URI already exists"
                }, 500)
            logger.info("Successfully saved transaction to database")
        except Exception as e:
            logger.error(f"Failed to save transaction: {str(e)}")
            return cors_jsonify({
                "SUCCESS": False,
                "message": f"Database error: {str(e)}"
            }, 500)

        # Generate the URL
        url = f"https://t.me/MyMTLWalletBot?start=uri_{key}"
        logger.info(f"Generated URL: {url}")

        return cors_jsonify({
            "SUCCESS": True,
            "url": url
        }, 200)
    except Exception as e:
        logger.error(f"Unexpected error processing URI: {str(e)}", exc_info=True)
        return cors_jsonify({
            "SUCCESS": False,
            "message": f"Error processing URI: {str(e)}",
            "traceback": traceback.format_exc()
        }, 500)


@blueprint.route('/get/<uuid_key>', methods=['GET', 'OPTIONS'])
async def get(uuid_key):
    """
    Retrieves a saved URI by its UUID key.
    
    Parameters:
    - uuid_key: The UUID key of the saved URI
    
    Returns :
    - JSON with the URI if found
    - 404 if not found
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return cors_jsonify({})

    try:
        async with current_app.db_pool() as db_session:
            result = await db_session.execute(select(MMWBTransactions.json).filter(
                MMWBTransactions.uuid == uuid_key
            ))
            transaction_json = result.scalars().first()
        if not transaction_json:
            return cors_jsonify({
                "SUCCESS": False,
                "message": "URI not found"
            }, 404)

        data = json.loads(transaction_json)
        uri = data.get('uri')

        if not uri:
            return cors_jsonify({
                "SUCCESS": False,
                "message": "URI data is corrupted"
            }, 500)

        return cors_jsonify({
            "SUCCESS": True,
            "uri": uri
        }, 200)
    except Exception as e:
        return cors_jsonify({
            "SUCCESS": False,
            "message": f"Error retrieving URI: {str(e)}"
        }, 500)


@blueprint.route('/parse-uri', methods=['POST', 'OPTIONS'])
async def parse_uri():
    """
    Parse Stellar URI and replace sourceAccount with provided address.
    
    Accepts:
    - uri: Stellar URI string
    - account: Stellar account address to replace sourceAccount
    
    Returns:
    - JSON with XDR for signing and callback URL
    """
    if request.method == 'OPTIONS':
        return cors_jsonify({})

    try:
        data = await request.json
        uri = data.get('uri')
        account = data.get('account')

        if not uri:
            return cors_jsonify({
                "SUCCESS": False,
                "message": "URI is required"
            }, 400)

        logger.info(f"Parsing URI: {uri[:100]}...")
        if account:
            logger.info(f"Target account: {account}")

        # Parse URI to extract XDR and callback
        parsed_uri = urlparse(uri)
        query_params = parse_qs(parsed_uri.query)

        # Extract XDR parameter
        xdr_param = query_params.get('xdr', [None])[0]
        if not xdr_param:
            return cors_jsonify({
                "SUCCESS": False,
                "message": "No XDR found in URI"
            }, 400)

        # URL decode XDR
        decoded_xdr = unquote(xdr_param)
        logger.debug(f"Decoded XDR: {decoded_xdr[:50]}...")

        # Parse the transaction envelope
        try:
            transaction_envelope = TransactionEnvelope.from_xdr(decoded_xdr, Network.PUBLIC_NETWORK_PASSPHRASE)
            transaction = transaction_envelope.transaction
        except Exception as e:
            logger.error(f"Failed to parse XDR: {str(e)}")
            return cors_jsonify({
                "SUCCESS": False,
                "message": f"Invalid XDR format: {str(e)}"
            }, 400)

        # Extract callback URL from query parameters
        callback_url = None
        if 'callback' in query_params:
            callback_param = query_params['callback'][0]
            if callback_param.startswith('url:'):
                callback_url = callback_param[4:]

        if not callback_url:
            return cors_jsonify({
                "SUCCESS": False,
                "message": "No callback URL found in URI"
            }, 400)

        logger.info(f"Callback URL: {callback_url}")

        # If no account provided, just return callback URL
        if not account:
            return cors_jsonify({
                "SUCCESS": True,
                "callback_url": callback_url,
                "message": "URI parsed successfully"
            }, 200)

        # Create new transaction with replaced source account
        try:
            # Import Account class and TimeBounds
            from stellar_sdk import Account, TimeBounds
            import time
            
            # Create account object for the new account
            source_account = Account(account, -1)  # -1 means we don't know the sequence number

            # Create new transaction builder
            builder = TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                base_fee=transaction.fee
            )
            
            # Add time bounds (required for SEP-07)
            current_time = int(time.time())
            builder.add_time_bounds(current_time, current_time + 300)  # 5 minutes validity

            # Copy operations from original transaction
            for operation in transaction.operations:
                builder.append_operation(operation)

            # Copy memo if it exists
            if hasattr(transaction, 'memo') and transaction.memo:
                builder.add_memo(transaction.memo)

            # Build the new transaction
            new_transaction = builder.build()

            # Convert to XDR for signing
            new_xdr = new_transaction.to_xdr()

            logger.info(f"Successfully created new XDR for account: {account}")

            return cors_jsonify({
                "SUCCESS": True,
                "xdr": new_xdr,
                "callback_url": callback_url,
                "message": "XDR generated successfully"
            }, 200)

        except Exception as e:
            logger.error(f"Failed to create new transaction: {str(e)}")
            return cors_jsonify({
                "SUCCESS": False,
                "message": f"Failed to create transaction: {str(e)}"
            }, 500)

    except Exception as e:
        logger.error(f"Unexpected error parsing URI: {str(e)}", exc_info=True)
        return cors_jsonify({
            "SUCCESS": False,
            "message": f"Error parsing URI: {str(e)}"
        }, 500)


@blueprint.route('/submit-signed', methods=['POST', 'OPTIONS'])
async def submit_signed():
    """
    Submit signed XDR to callback URL.
    
    Accepts:
    - signed_xdr: Signed XDR string
    - callback_url: URL to submit to
    
    Returns:
    - JSON with submission result
    """
    if request.method == 'OPTIONS':
        return cors_jsonify({})

    try:
        data = await request.json
        signed_xdr = data.get('signed_xdr')
        callback_url = data.get('callback_url')

        if not signed_xdr or not callback_url:
            return cors_jsonify({
                "SUCCESS": False,
                "message": "signed_xdr and callback_url are required"
            }, 400)

        logger.info(f"Submitting signed XDR to: {callback_url}")

        # Validate signed XDR format
        if not is_valid_base64(signed_xdr):
            return cors_jsonify({
                "SUCCESS": False,
                "message": "Invalid signed XDR format"
            }, 400)

        # Submit to callback URL using form data
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field('xdr', signed_xdr)

                async with session.post(callback_url, data=form_data) as response:
                    response_text = await response.text()

                    logger.info(f"Callback response status: {response.status}")
                    logger.debug(f"Callback response: {response_text}")

                    if response.status == 200:
                        return cors_jsonify({
                            "SUCCESS": True,
                            "message": "Successfully submitted to callback",
                            "callback_response": response_text
                        }, 200)
                    else:
                        return cors_jsonify({
                            "SUCCESS": False,
                            "message": f"Callback returned status {response.status}",
                            "callback_response": response_text
                        }, response.status)

        except Exception as e:
            logger.error(f"Failed to submit to callback: {str(e)}")
            return cors_jsonify({
                "SUCCESS": False,
                "message": f"Failed to submit to callback: {str(e)}"
            }, 500)

    except Exception as e:
        logger.error(f"Unexpected error submitting signed XDR: {str(e)}", exc_info=True)
        return cors_jsonify({
            "SUCCESS": False,
            "message": f"Error submitting signed XDR: {str(e)}"
        }, 500)


@blueprint.route("/hand")
@blueprint.route("/hand/")
async def auth_hand():
    return await render_template('sep07hand.html')


if __name__ == '__main__':
    print(asyncio.run(print('GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI')))
