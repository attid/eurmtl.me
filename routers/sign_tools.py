import json
import os
from datetime import datetime
from random import shuffle

import requests
from loguru import logger
from quart import Markup, jsonify, Blueprint, request, render_template, flash, session, redirect, abort, url_for
from sqlalchemy import func
from stellar_sdk import DecoratedSignature, Keypair, Network, TransactionEnvelope
from stellar_sdk.exceptions import BadSignatureError
from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
from stellar_sdk.sep import stellar_uri

from db.sql_models import Transactions, Signers, Signatures, Alerts
from db.sql_pool import db_pool
from other.cache_tools import async_cache_with_ttl
from other.config_reader import start_path, config
from other.grist_tools import load_user_from_grist
from other.stellar_tools import (decode_xdr_to_text, check_publish_state, check_user_in_sign,
                                 add_transaction)
from other.telegram_tools import skynet_bot

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

    with db_pool() as db_session:
        if len(tr_hash) == 64:
            transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
        else:
            transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()

    if transaction is None:
        return 'Transaction not exist =('

    transaction_env = TransactionEnvelope.from_xdr(transaction.body,
                                                   network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)

    admin_weight = 2 if await check_user_in_sign(tr_hash) else 0
    if 'userdata' in session and 'username' in session['userdata']:
        user_id = int(session['userdata']['id'])
        with db_pool() as db_session:
            alert = db_session.query(Alerts).filter(Alerts.transaction_hash == tr_hash,
                                                    Alerts.tg_id == user_id).first()
    else:
        user_id = 0
        alert = False

    try:
        json_transaction = json.loads(transaction.json)
    except:
        await flash('BAD xdr. Can`t load')
        resp = await render_template('tabler_sign_add.html', tx_description='', tx_body='')
        return resp

    if request.method == 'POST':
        form_data = await request.form
        tx_body = form_data.get('tx_body') or form_data.get('xdr')
        signature_id = form_data.get('signature_id')
        hide_action = form_data.get('hide')

        if signature_id and hide_action is not None:
            # Проверяем, является ли пользователь администратором
            if admin_weight > 0:
                hide = 1 if hide_action == 'true' else 0
                with db_pool() as db_session:
                    signature_to_update = db_session.query(Signatures).filter(Signatures.id == signature_id).first()
                    if signature_to_update:
                        signature_to_update.hidden = hide
                        db_session.commit()
            else:
                await flash('You do not have permission to perform this action.')

        # дальше уже только если есть tx_body
        if tx_body is not None:
            result = await parse_xdr_for_signatures(tx_body)

            # Обработка результатов
            if result["SUCCESS"]:
                # Если SUCCESS == True, обработать каждое сообщение как 'good'
                for msg in result["MESSAGES"]:
                    await flash(msg, 'good')
            else:
                # Если SUCCESS == False, обработать каждое сообщение без указания категории
                for msg in result["MESSAGES"]:
                    await flash(msg)

    signers_table = []
    bad_signers = []
    signatures = []
    for address in json_transaction:
        signers = []
        has_votes = 0
        # find bad signer and calc votes
        sorted_signers = sorted(json_transaction[address]['signers'], key=lambda x: x[1])
        for signer in sorted_signers:
            with db_pool() as db_session:
                signature = db_session.query(Signatures).join(Signers, Signatures.signer_id == Signers.id).filter(
                    Signatures.transaction_hash == transaction.hash,
                    Signers.public_key == signer[0],
                    Signatures.hidden != 1
                ).first()
                db_signer: Signers = db_session.query(Signers).filter(Signers.public_key == signer[0]).first()
                signature_dt = db_session.query(Signatures).join(Signers, Signatures.signer_id == Signers.id).filter(
                    Signers.public_key == signer[0]).order_by(Signatures.add_dt.desc()).first()
                user = await load_user_from_grist(account_id=db_signer.public_key) if db_signer else None
                username = user.username if user else None
                signature_days = (datetime.now() - signature_dt.add_dt).days if signature_dt else "Never"
            if signature:
                if has_votes < int(json_transaction[address]['threshold']) or int(
                        json_transaction[address]['threshold']) == 0:
                    # await flash(json_transaction[address]['threshold'], 'good')
                    signature_xdr = DecoratedSignature.from_xdr_object(
                        DecoratedSignatureXdr.from_xdr(signature.signature_xdr))
                    if signature_xdr not in transaction_env.signatures:
                        transaction_env.signatures.append(signature_xdr)
                has_votes += signer[1]
            else:
                bad_signers.append(username)
            if signer[1] > 0:
                signers.append([signer[0], username, signature_days, signer[1], signature])
        signers.sort(key=lambda k: k[3], reverse=True)

        signers_table.append({
            "threshold": json_transaction[address]['threshold'],
            "sources": address,
            "has_votes": has_votes,
            "signers": signers
        })

    # show signatures
    with db_pool() as db_session:
        db_signatures = db_session.query(Signatures) \
            .outerjoin(Signers, Signatures.signer_id == Signers.id) \
            .filter(Signatures.transaction_hash == transaction.hash).order_by(Signatures.id).all()
        for signature in db_signatures:
            signer:Signers = db_session.query(Signers).filter(
                Signers.id == signature.signer_id).first()
            user = await load_user_from_grist(account_id=signer.public_key) if signer else None
            username = user.username if user else None
            signatures.append([signature.id, signature.add_dt, username, signature.signature_xdr, signature.hidden])
    #    from stellar_sdk import DecoratedSignature
    #    from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
    #    transaction_env.signatures.append(
    #        DecoratedSignature.from_xdr_object(DecoratedSignatureXdr.from_xdr(signature.signature_xdr)))
    # await flash(transaction.json)

    # try send
    send = request.args.get('send', default=None)
    if send is not None:
        try:
            if request.args.get('random', default=None) is not None:
                shuffle(transaction_env.signatures)
                await flash('Signatures shuffled', 'good')

            transaction_resp = requests.post('https://horizon.stellar.org/transactions/',
                                             data={"tx": transaction_env.to_xdr()})
            if transaction_resp.status_code == 200:
                await flash(f'Successfully sent, accepted : {transaction_resp.json()["successful"]}', 'good')
            else:
                await flash(f'Failed to send. {transaction_resp.json()["extras"]["result_codes"]}')
                result_codes = transaction_resp.json().get("extras", {}).get("result_codes", {})
                operation_results = result_codes.get("operations", [])

                # Находим первую операцию, которая не является 'op_success'
                for i, result in enumerate(operation_results):
                    if result != 'op_success':
                        await flash(f'Error in operation {i}: {result}')

                        failed_operation_dict = '<br>'.join(
                            await decode_xdr_to_text(transaction.body, only_op_number=i))
                        await flash(Markup(f'Details of failed operation: {failed_operation_dict}'))

                        break

        except Exception as e:
            await flash("Failed to send. The error is unclear")
            await flash(f'{e}')

    resp = await render_template('tabler_sign_sign.html', tx_description=transaction.description,
                                 tx_body=transaction.body, tx_hash=transaction.hash, user_id=user_id,
                                 bad_signers=set(bad_signers), signatures=signatures,
                                 signers_table=signers_table, uuid=transaction.uuid, alert=alert,
                                 tx_full=transaction_env.to_xdr(), admin_weight=admin_weight,
                                 publish_state=check_publish_state(transaction.hash))
    return resp


async def parse_xdr_for_signatures(tx_body):
    result = {"SUCCESS": False,
              "MESSAGES": []}
    try:
        tr_full: TransactionEnvelope = TransactionEnvelope.from_xdr(tx_body,
                                                                    network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        # Добавляем хеш транзакции в результат
        result["hash"] = tr_full.hash_hex()
    except:
        result['MESSAGES'].append('BAD xdr. Can`t load')
        return result

    with db_pool() as db_session:
        transaction = db_session.query(Transactions).filter(Transactions.hash == tr_full.hash_hex()).first()
        if transaction is None:
            result['MESSAGES'].append('Transaction not found')
            return result
    try:
        json_transaction = json.loads(transaction.json)
    except:
        result['MESSAGES'].append('Can`t load json')
        return result

    if len(tr_full.signatures) > 0:
        with db_pool() as db_session:
            for signature in tr_full.signatures:
                signer: Signers = db_session.query(Signers).filter(
                    Signers.signature_hint == signature.signature_hint.hex()).first()
                user = await load_user_from_grist(account_id=signer.public_key) if signer else None
                username = user.username if user else None
                if db_session.query(Signatures).filter(Signatures.transaction_hash == transaction.hash,
                                                       Signatures.signature_xdr == signature.to_xdr_object(
                                                       ).to_xdr()).first():
                    result['MESSAGES'].append(f'Can`t add {username if signer else None}. '
                                              f'Already was added.')
                else:
                    # check is good ?
                    all_sign = []
                    for record in json_transaction:
                        all_sign.extend(json_transaction[record]['signers'])
                    json_signer = list(filter(lambda x: x[2] == signature.signature_hint.hex(), all_sign))
                    if len(json_signer) == 0:
                        result['MESSAGES'].append(f'Bad signature. {signature.signature_hint.hex()} not found')
                    else:
                        user_keypair = Keypair.from_public_key(json_signer[0][0])
                        try:
                            user_keypair.verify(data=tr_full.hash(), signature=signature.signature)
                            db_session.add(Signatures(signature_xdr=signature.to_xdr_object().to_xdr(),
                                                      signer_id=signer.id if signer else None,
                                                      transaction_hash=transaction.hash))
                            text = f'Added signature from {username}'
                            result['MESSAGES'].append(text)
                            result['SUCCESS'] = True
                            await alert_singers(tr_hash=transaction.hash, small_text=text,
                                          tx_description=transaction.description)
                        except BadSignatureError:
                            result['MESSAGES'].append(f'Bad signature. {signature.signature_hint.hex()} not verify')
            db_session.commit()
    return result


@blueprint.route('/sign_all', methods=('GET', 'POST'))
@blueprint.route('/sign_all/', methods=('GET', 'POST'))
async def start_show_all_transactions():
    next_page = request.args.get('next', default=0, type=int)
    limit = 100
    offset = next_page * limit

    with db_pool() as db_session:
        transactions_query = db_session.query(
            Transactions.hash.label('hash'),
            Transactions.description.label('description'),
            Transactions.add_dt.label('add_dt'),
            Transactions.state.label('state'),
            func.count(Signatures.signature_xdr).label('signature_count')
        ).outerjoin(
            Signatures, Transactions.hash == Signatures.transaction_hash
        ).group_by(Transactions).order_by(Transactions.add_dt.desc())

        transactions = transactions_query.offset(offset).limit(limit).all()
        next_page = next_page + 1 if len(transactions) == limit else None

        return await render_template('tabler_sign_all.html', transactions=transactions, next_page=next_page)


@blueprint.route('/decode/<tr_hash>', methods=('GET', 'POST'))
async def decode_xdr(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        abort(404)

    with db_pool() as db_session:
        if len(tr_hash) == 64:
            transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
        else:
            transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()

    if transaction is None:
        return 'Transaction not exist =('

    encoded_xdr = await decode_xdr_to_text(transaction.body)
    return ('<br>'.join(encoded_xdr) + '<br><br><br>').replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')


@async_cache_with_ttl(ttl_seconds=7*24*60*60, maxsize=30)  # Кеш на неделю с лимитом 30 транзакций
async def create_transaction_uri(tr_hash):
    """
    Создает URI для транзакции с использованием TransactionStellarUri.
    
    Args:
        tr_hash: Хеш транзакции
        
    Returns:
        str: URI транзакции для использования в QR-коде или None, если транзакция не найдена
    """
    with db_pool() as db_session:
        if len(tr_hash) == 64:
            transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
        else:
            transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()
    
    if not transaction:
        return None
        
    # Получаем транзакцию из XDR
    transaction_envelope = TransactionEnvelope.from_xdr(transaction.body, Network.PUBLIC_NETWORK_PASSPHRASE)
    
    # Ограничиваем описание до 300 символов для параметра msg
    msg = transaction.description[:300] if transaction.description else None
    
    # Создаем URI с колбеком и описанием в msg
    transaction_uri = stellar_uri.TransactionStellarUri(
        transaction_envelope=transaction_envelope,
        callback="https://eurmtl.me/remote/sep07",
        origin_domain="eurmtl.me",
        message=msg
    )

    transaction_uri.sign(config.domain_key.get_secret_value())

    return transaction_uri.to_uri()


@blueprint.route('/uri_qr/<tr_hash>', methods=('GET', 'POST'))
async def generate_transaction_qr(tr_hash):
    """
    Генерирует QR-код для транзакции, превращая её в URI.
    QR-код сохраняется в static/qr/хеш_транзакции.png
    """
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        return jsonify({
            'success': False,
            'message': 'Invalid transaction hash',
            'file': '',
            'uri': ''
        })

    # Путь для сохранения QR-кода
    qr_file_path = f'/static/qr/{tr_hash}.png'
    full_path = start_path + qr_file_path

    # Получаем URI для транзакции
    uri = await create_transaction_uri(tr_hash)
    
    if uri is None:
        return jsonify({
            'success': False,
            'message': 'Transaction not found',
            'file': '',
            'uri': ''
        })

    # Если файл уже существует, не генерируем его заново
    if os.path.exists(full_path+'88'):
        return jsonify({
            'success': True,
            'message': 'QR code already exists',
            'file': qr_file_path,
            'uri': uri
        })

    try:
        # Получаем транзакцию для получения описания
        with db_pool() as db_session:
            if len(tr_hash) == 64:
                transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
            else:
                transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()
        
        # URI уже получен выше через create_transaction_uri
        
        # Получаем первые целые слова описания транзакции (не более 10 символов)
        text_for_qr = "Transaction"
        if transaction and transaction.description:
            words = transaction.description.split()
            text = ""
            for word in words:
                if len(text + " " + word if text else word) <= 10:
                    text = text + " " + word if text else word
                else:
                    break
            text_for_qr = text if text else words[0][:10]  # Если одно слово больше 10 символов, берем первые 10
        
        # Создаем QR-код
        from routers.helpers import create_beautiful_code
        create_beautiful_code(qr_file_path, text_for_qr, uri)
        
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

    # if not await check_user_in_sign(tr_hash):
    #     return jsonify({'success': False, 'message': 'User not found in signers'})

    try:
        with db_pool() as db_session:
            alert = db_session.query(Alerts).filter(Alerts.transaction_hash == tr_hash,
                                                    Alerts.tg_id == tg_id).first()
            if alert is None:
                alert = Alerts(tg_id=tg_id, transaction_hash=tr_hash)
                db_session.add(alert)
                db_session.commit()
                return jsonify({
                    'success': True,
                    'icon': 'ti-bell-ringing',
                    'message': 'Alert added successfully'
                })
            else:
                db_session.delete(alert)
                db_session.commit()
                return jsonify({
                    'success': True,
                    'icon': 'ti-bell-off',
                    'message': 'Alert removed successfully'
                })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })


async def alert_singers(tr_hash, small_text, tx_description):
    text = (f'Transaction <a href="https://eurmtl.me/sign_tools/{tr_hash}">{tx_description}</a> : '
            f'{small_text}.')
    with db_pool() as db_session:
        alert_query = db_session.query(Alerts).filter(Alerts.transaction_hash == tr_hash).all()
        for alert in alert_query:
            await skynet_bot.send_message(chat_id=alert.tg_id, text=text, disable_web_page_preview=True, parse_mode='HTML')


if __name__ == '__main__':
    x9dr = 'AA'
    # r = asyncio.run(parse_xdr_for_signatures(xdr))
