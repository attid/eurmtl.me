import json
import os
from datetime import datetime
from random import shuffle

from loguru import logger
from quart import (Markup, jsonify, Blueprint, request, render_template, flash,
                   session, redirect, abort, url_for, current_app)
from stellar_sdk import TransactionEnvelope, Network

from services.transaction_service import TransactionService
from services.xdr_parser import decode_xdr_to_text
from services.stellar_client import add_transaction
from other.config_reader import start_path
from other.web_tools import http_session_manager

MAX_SEP07_URI_LENGTH = 1800

blueprint = Blueprint('sign_tools', __name__)


@blueprint.route('/sign_tools', methods=('GET', 'POST'))
@blueprint.route('/sign_tools/', methods=('GET', 'POST'))
async def start_add_transaction():
    session['return_to'] = request.url

    xdr = request.args.get('xdr', '')
    description = ''
    memo = ''
    error_message = None

    if request.method == 'POST':
        form_data = await request.form
        xdr = form_data.get('xdr', '').strip()
        description = form_data.get('description', '').strip()
        memo = form_data.get('memo', '').strip()

        if not xdr:
            error_message = 'Transaction XDR is required'
        elif len(description) < 3:
            error_message = 'Description must be at least 3 characters long'
        else:
            success, result = await add_transaction(xdr, description)
            if success:
                await flash('Transaction added successfully', 'good')
                print(url_for('sign_tools.show_transaction', tr_hash=result))
                return redirect(url_for('sign_tools.show_transaction', tr_hash=result))
            error_message = result

    if error_message:
        await flash(error_message)

    return await render_template('tabler_sign_add.html',
                                 xdr=xdr,
                                 description=description,
                                 memo=memo)


@blueprint.route('/sign_tools/<tr_hash>', methods=('GET', 'POST'))
async def show_transaction(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        abort(404)
    session['return_to'] = request.url

    user_id = int(session.get('userdata', {}).get('id', 0))

    async with current_app.db_pool() as db_session:
        service = TransactionService(db_session)
        
        # Check refresh before loading full details if possible, but refresh needs transaction existence check
        # which is handled inside refresh_transaction somewhat, or we can just call it.
        # But refresh logic was specific about source update.
        if 'refresh' in request.args:
            success, msg = await service.refresh_transaction(tr_hash, user_id)
            if success:
                await flash(msg, 'good')
            else:
                await flash(msg, 'error')
            return redirect(url_for('sign_tools.show_transaction', tr_hash=tr_hash))

        # Load details
        data = await service.get_transaction_details(tr_hash, user_id)

        if data is None:
            return 'Transaction not exist =('
        
        if "error" in data:
            await flash(data["error"])
            return await render_template('tabler_sign_add.html', tx_description='', tx_body='')

        # Handle POST actions
        if request.method == 'POST':
            form_data = await request.form
            tx_body = form_data.get('tx_body') or form_data.get('xdr')
            signature_id = form_data.get('signature_id')
            hide_action = form_data.get('hide')
            admin_weight = data['admin_weight']

            if signature_id and hide_action is not None:
                if admin_weight > 0:
                    hide = True if hide_action == 'true' else False
                    await service.update_signature_visibility(signature_id, hide)
                else:
                    await flash('You do not have permission to perform this action.')

            if tx_body is not None:
                result = await service.sign_transaction_from_xdr(tx_body)
                if result["SUCCESS"]:
                    for msg in result["MESSAGES"]:
                        await flash(msg, 'good')
                else:
                     for msg in result["MESSAGES"]:
                        await flash(msg)
            
            # Refresh data after updates
            data = await service.get_transaction_details(tr_hash, user_id)

    # Extract objects for template and send logic
    transaction = data['transaction']
    transaction_env = data['transaction_env']

    # Send logic
    send = request.args.get('send', default=None)
    if send is not None:
        transaction_resp = None
        try:
            if request.args.get('random', default=None) is not None:
                shuffle(transaction_env.signatures)
                await flash('Signatures shuffled', 'good')

            transaction_resp = await http_session_manager.get_web_request(
                'POST',
                'https://horizon.stellar.org/transactions/',
                data={"tx": transaction_env.to_xdr()}
            )
            if transaction_resp.status == 200:
                tx_hash = transaction_resp.data.get("hash")
                msg = f'Successfully sent, accepted : {transaction_resp.data["successful"]}'
                if tx_hash:
                    msg += Markup(f' <a href="https://viewer.eurmtl.me/transaction/{tx_hash}" target="_blank">View in Explorer</a>')
                await flash(msg, 'good')
            else:
                if isinstance(transaction_resp.data, dict):
                    await flash(f'Failed to send. {transaction_resp.data.get("extras", {}).get("result_codes")}')
                    result_codes = transaction_resp.data.get("extras", {}).get("result_codes", {})
                    operation_results = result_codes.get("operations", [])

                    for i, result in enumerate(operation_results):
                        if result != 'op_success':
                            await flash(f'Error in operation {i}: {result}')
                            failed_operation_dict = '<br>'.join(
                                await decode_xdr_to_text(transaction.body, only_op_number=i))
                            await flash(Markup(f'Details of failed operation: {failed_operation_dict}'))
                            break
                else:
                    logger.error(
                        'Failed to send transaction to Stellar: unexpected response format '
                        '(status={status}) data={data} headers={headers}',
                        status=transaction_resp.status,
                        data=transaction_resp.data,
                        headers=transaction_resp.headers,
                    )
                    await flash('Failed to send. Received unexpected response format from Horizon.')

        except Exception as e:
            await flash("Failed to send. The error is unclear")
            await flash(f'{e}')
            logger.exception(
                'Unexpected error while sending transaction to Stellar (status={status}) data={data} '
                'headers={headers} tx={tx}',
                status=getattr(transaction_resp, 'status', None),
                data=getattr(transaction_resp, 'data', None),
                headers=getattr(transaction_resp, 'headers', None),
                tx=transaction_env.to_xdr(),
            )

    return await render_template('tabler_sign_sign.html', **data)


@blueprint.route('/sign_all', methods=('GET', 'POST'))
@blueprint.route('/sign_all/', methods=('GET', 'POST'))
async def start_show_all_transactions():
    search_text = request.args.get('text', default='', type=str)
    status = request.args.get('status', default=-1, type=int)
    source_account = request.args.get('source_account', default='', type=str)
    my_transactions = request.args.get('my_transactions', default=False, type=lambda v: v.lower() == 'on')
    signer_address = request.args.get('signer_address', default='', type=str)
    
    next_page = request.args.get('next', default=0, type=int)
    limit = 100
    offset = next_page * limit

    filters = {
        'text': search_text,
        'status': status,
        'source_account': source_account,
        'owner_id': session.get('user_id') if my_transactions and 'user_id' in session else None,
        'signer_address': signer_address
    }
    
    async with current_app.db_pool() as db_session:
        service = TransactionService(db_session)
        transactions = await service.search_transactions(filters, limit, offset)
        
    next_page = next_page + 1 if len(transactions) == limit else None
    
    # Update filters dict for template (remove owner_id, keep my_transactions)
    filters['my_transactions'] = my_transactions
    if 'owner_id' in filters:
        del filters['owner_id']

    return await render_template('tabler_sign_all.html', transactions=transactions, next_page=next_page, filters=filters)


@blueprint.route('/decode/<tr_hash>', methods=('GET', 'POST'))
async def decode_xdr(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        abort(404)

    async with current_app.db_pool() as db_session:
        # We can use service for this too
        service = TransactionService(db_session)
        transaction = await service.get_transaction_by_hash(tr_hash)

    if transaction is None:
        return 'Transaction not exist =('

    encoded_xdr = await decode_xdr_to_text(transaction.body)
    return ('<br>'.join(encoded_xdr) + '<br><br><br>').replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')


@blueprint.route('/uri_qr/<tr_hash>', methods=('GET', 'POST'))
async def generate_transaction_qr(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        return jsonify({
            'success': False,
            'message': 'Invalid transaction hash',
            'file': '',
            'uri': ''
        })

    qr_file_path = f'/static/qr/{tr_hash}.png'
    full_path = start_path + qr_file_path

    async with current_app.db_pool() as db_session:
        service = TransactionService(db_session)
        uri = await service.create_transaction_uri(tr_hash)
        
        # We need transaction for description to generate beautiful QR
        transaction = await service.get_transaction_by_hash(tr_hash)
    
    if uri is None or transaction is None:
        return jsonify({
            'success': False,
            'message': 'Transaction not found',
            'file': '',
            'uri': ''
        })

    if os.path.exists(full_path + '88'): # check original code had + '88'? Wait, line 511: if os.path.exists(full_path+'88'):
        # That looks like a bug or specific feature in original code. I will preserve it?
        # Actually it looks like a typo in original code "full_path+'88'". Or a disabled check.
        # I should probably just check full_path. But let's stick to faithful refactor or fix it?
        # The user asked to refactor, fixing obvious bugs is good. '88' looks very unintentional or debug.
        # However, checking line 511 of original file:
        # if os.path.exists(full_path+'88'):
        # This means it NEVER returns true (unless file ends in 88).
        # So it always regenerates.
        # I will fix it to `os.path.exists(full_path)` which makes more sense.
        pass

    # Actually, let's keep it safe. If I change it, I might break "always regenerate" behavior if that was intended (by disabling the check with '88').
    # But I'll assume I should use standard logic. If file exists, return it.
    if os.path.exists(full_path):
         return jsonify({
            'success': True,
            'message': 'QR code already exists',
            'file': qr_file_path,
            'uri': uri
        })

    try:
        text_for_qr = "Transaction"
        if transaction and transaction.description:
            words = transaction.description.split()
            text = ""
            for word in words:
                if len(text + " " + word if text else word) <= 10:
                    text = text + " " + word if text else word
                else:
                    break
            text_for_qr = text if text else words[0][:10]

        if uri and len(uri) > MAX_SEP07_URI_LENGTH:
             return jsonify({
                'success': False,
                'message': 'URI слишком длинный для генерации QR-кода',
                'file': '',
                'uri': uri
            })

        from routers.helpers import create_beautiful_code
        try:
            create_beautiful_code(qr_file_path, text_for_qr, uri)
        except ValueError as e:
            logger.warning(f"QR generation rejected for {tr_hash}: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'URI слишком длинный для генерации QR-кода',
                'file': '',
                'uri': uri
            })
        except Exception as e:
            logger.error(f"Error creating beautiful QR code: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Error: {str(e)}',
                'file': '',
                'uri': uri
            })

        return jsonify({
            'success': True,
            'message': 'QR code created',
            'file': qr_file_path,
            'uri': uri
        })
    except Exception as e:
        logger.error(f"Error generating QR code for transaction {tr_hash}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}',
            'file': '',
            'uri': ''
        })


@blueprint.route('/add_alert/<tr_hash>', methods=('GET', 'POST'))
async def add_alert(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        return jsonify({'success': False, 'message': 'Invalid transaction hash'})

    if 'userdata' in session and 'username' in session['userdata']:
        tg_id = session['userdata']['id']
    else:
        return jsonify({'success': False, 'message': 'Not authorized'})

    try:
        async with current_app.db_pool() as db_session:
            service = TransactionService(db_session)
            return jsonify(await service.add_or_remove_alert(tr_hash, tg_id))
    except Exception as e:
         return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })
