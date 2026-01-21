import json
import os
from datetime import datetime
from random import shuffle

from loguru import logger
from quart import (Markup, jsonify, Blueprint, request, render_template, flash,
                   session, redirect, abort, url_for, current_app)
from sqlalchemy import func, text, select
from stellar_sdk import DecoratedSignature, Keypair, Network, TransactionEnvelope
from stellar_sdk.exceptions import BadSignatureError
from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
from stellar_sdk.sep import stellar_uri

from db.sql_models import Transactions, Signers, Signatures, Alerts
from infrastructure.repositories.transaction_repository import TransactionRepository
from other.cache_tools import async_cache_with_ttl
from other.config_reader import start_path, config
from other.grist_tools import load_users_from_grist
from other.stellar_tools import (decode_xdr_to_text, check_publish_state, check_user_in_sign,
                                 add_transaction, update_transaction_sources)
from other.telegram_tools import skynet_bot
from other.web_tools import http_session_manager

MAX_SEP07_URI_LENGTH = 1800  # QR version=5 + H коррекция стабильно вмещают ~1.8k символов

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

    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        if len(tr_hash) == 64:
            transaction = await repo.get_by_hash(tr_hash)
        else:
            transaction = await repo.get_by_uuid(tr_hash)

    if transaction is None:
        return 'Transaction not exist =('

    # Проверяем, есть ли GET-параметр ?refresh
    if 'refresh' in request.args:
        # Проверяем права доступа
        admin_weight_for_refresh = 2 if await check_user_in_sign(tr_hash) else 0
        is_owner = 'userdata' in session and transaction.owner_id and int(transaction.owner_id) == int(session['userdata']['id'])

        if admin_weight_for_refresh > 0 or is_owner:
            success = await update_transaction_sources(transaction)
            if success:
                await flash('Информация о подписантах и порогах успешно обновлена!', 'good')
            else:
                await flash('Не удалось обновить информацию о подписантах.', 'error')
            return redirect(url_for('sign_tools.show_transaction', tr_hash=tr_hash))
        else:
            await flash('У вас нет прав для выполнения этого действия.', 'error')
            return redirect(url_for('sign_tools.show_transaction', tr_hash=tr_hash))

    transaction_env = TransactionEnvelope.from_xdr(transaction.body,
                                                   network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)

    admin_weight = 2 if await check_user_in_sign(tr_hash) else 0
    if 'userdata' in session and 'username' in session['userdata']:
        user_id = int(session['userdata']['id'])
        async with current_app.db_pool() as db_session:
            result = await db_session.execute(select(Alerts).filter(Alerts.transaction_hash == tr_hash,
                                                    Alerts.tg_id == user_id))
            alert = result.scalars().first()
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
                async with current_app.db_pool() as db_session:
                    result = await db_session.execute(select(Signatures).filter(Signatures.id == signature_id))
                    signature_to_update = result.scalars().first()
                    if signature_to_update:
                        signature_to_update.hidden = hide
                        await db_session.commit()
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

    # Предзагрузка всех пользователей Grist для оптимизации
    all_public_keys = [signer[0] for address in json_transaction for signer in json_transaction[address]['signers']]
    user_map = await load_users_from_grist(all_public_keys)

    signers_table = []
    bad_signers = []
    signatures = []
    for address in json_transaction:
        signers = []
        has_votes = 0
        # find bad signer and calc votes
        sorted_signers = sorted(json_transaction[address]['signers'], key=lambda x: x[1])
        sorted_signers = sorted(json_transaction[address]['signers'], key=lambda x: x[1])
        for signer in sorted_signers:
            async with current_app.db_pool() as db_session:
                repo = TransactionRepository(db_session)
                signature = await repo.get_signature_by_signer_public_key(signer[0], transaction.hash)
                
                db_signer = await repo.get_signer_by_public_key(signer[0])
                
                signature_dt = await repo.get_latest_signature_by_signer(signer[0])
                
                signature_source_dt = await repo.get_latest_signature_for_source(signer[0], address)

                user = user_map.get(db_signer.public_key) if db_signer else None
                username = user.username if user else None

                signature_days_any = (datetime.now() - signature_dt.add_dt).days if signature_dt else None
                signature_days_source = (datetime.now() - signature_source_dt.add_dt).days if signature_source_dt else None
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
                signers.append([
                    signer[0],
                    username,
                    {
                        "source": signature_days_source,
                        "any": signature_days_any
                    },
                    signer[1],
                    signature
                ])
        signers.sort(key=lambda k: k[3], reverse=True)

        signers_table.append({
            "threshold": json_transaction[address]['threshold'],
            "sources": address,
            "has_votes": has_votes,
            "signers": signers
        })

    # show signatures
    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        db_signatures = await repo.get_all_signatures_for_transaction(transaction.hash)
        
        # Оптимизация: предзагрузка всех пользователей для подписей
        signer_ids = [s.signer_id for s in db_signatures if s.signer_id]
        if signer_ids:
            result = await db_session.execute(select(Signers).filter(Signers.id.in_(signer_ids)))
            all_signers = result.scalars().all()
        else:
            all_signers = []
        signer_map = {s.id: s for s in all_signers}

        # Загружаем пользователей для подписей одним запросом
        signer_public_keys = [s.public_key for s in all_signers]
        user_map_signatures = await load_users_from_grist(signer_public_keys)

        for signature in db_signatures:
            signer_instance = signer_map.get(signature.signer_id)
            username = None
            if signer_instance:
                user = user_map_signatures.get(signer_instance.public_key)
                if user:
                    username = user.username
            
            signatures.append([signature.id, signature.add_dt, username, signature.signature_xdr, signature.hidden])
    #    from stellar_sdk import DecoratedSignature
    #    from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
    #    transaction_env.signatures.append(
    #        DecoratedSignature.from_xdr_object(DecoratedSignatureXdr.from_xdr(signature.signature_xdr)))
    # await flash(transaction.json)

    # try send
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
                await flash(f'Successfully sent, accepted : {transaction_resp.data["successful"]}', 'good')
            else:
                if isinstance(transaction_resp.data, dict):
                    await flash(f'Failed to send. {transaction_resp.data.get("extras", {}).get("result_codes")}')
                    result_codes = transaction_resp.data.get("extras", {}).get("result_codes", {})
                    operation_results = result_codes.get("operations", [])

                    # Находим первую операцию, которая не является 'op_success'
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

    resp = await render_template('tabler_sign_sign.html', tx_description=transaction.description,
                                 tx_body=transaction.body, tx_hash=transaction.hash, user_id=user_id,
                                 bad_signers=set(bad_signers), signatures=signatures,
                                 signers_table=signers_table, uuid=transaction.uuid, alert=alert,
                                 tx_full=transaction_env.to_xdr(), admin_weight=admin_weight,
                                 publish_state=await check_publish_state(transaction.hash))
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

    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        transaction = await repo.get_by_hash(tr_full.hash_hex())
        if transaction is None:
            result['MESSAGES'].append('Transaction not found')
            return result
    try:
        json_transaction = json.loads(transaction.json)
    except:
        result['MESSAGES'].append('Can`t load json')
        return result

    if len(tr_full.signatures) > 0:
        # Оптимизация: предзагрузка всех пользователей Grist
        all_signer_hints = [s.signature_hint.hex() for s in tr_full.signatures]
        async with current_app.db_pool() as db_session:
            result = await db_session.execute(select(Signers).filter(Signers.signature_hint.in_(all_signer_hints)))
            all_db_signers = result.scalars().all()
        
        signer_map = {s.signature_hint: s for s in all_db_signers}
        user_map = await load_users_from_grist([s.public_key for s in all_db_signers])

        async with current_app.db_pool() as db_session:
            for signature in tr_full.signatures:
                db_signer = signer_map.get(signature.signature_hint.hex())
                user = user_map.get(db_signer.public_key) if db_signer else None
                username = user.username if user else None

                result = await db_session.execute(select(Signatures).filter(Signatures.transaction_hash == transaction.hash,
                                                       Signatures.signature_xdr == signature.to_xdr_object(
                                                       ).to_xdr()))
                if result.scalars().first():
                    result['MESSAGES'].append(f'Can`t add {username if db_signer else None}. '
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
                                                      signer_id=db_signer.id if db_signer else None,
                                                      transaction_hash=transaction.hash))
                            text = f'Added signature from {username}'
                            result['MESSAGES'].append(text)
                            result['SUCCESS'] = True
                            await alert_singers(tr_hash=transaction.hash, small_text=text,
                                          tx_description=transaction.description)
                        except BadSignatureError:
                            result['MESSAGES'].append(f'Bad signature. {signature.signature_hint.hex()} not verify')
            await db_session.commit()
    return result


@blueprint.route('/sign_all', methods=('GET', 'POST'))
@blueprint.route('/sign_all/', methods=('GET', 'POST'))
async def start_show_all_transactions():
    # Получаем параметры фильтрации из запроса
    search_text = request.args.get('text', default='', type=str)
    status = request.args.get('status', default=-1, type=int)
    source_account = request.args.get('source_account', default='', type=str)
    my_transactions = request.args.get('my_transactions', default=False, type=lambda v: v.lower() == 'on')
    signer_address = request.args.get('signer_address', default='', type=str)
    
    next_page = request.args.get('next', default=0, type=int)
    limit = 100
    offset = next_page * limit

    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        transactions = await repo.search_transactions(
            search_text=search_text,
            status=status,
            source_account=source_account,
            owner_id=session['user_id'] if my_transactions and 'user_id' in session else None,
            signer_address=signer_address,
            offset=offset,
            limit=limit
        )
        next_page = next_page + 1 if len(transactions) == limit else None

        # Передаем параметры фильтров в шаблон
        filters = {
            'text': search_text,
            'status': status,
            'source_account': source_account,
            'my_transactions': my_transactions,
            'signer_address': signer_address
        }

        return await render_template('tabler_sign_all.html', transactions=transactions, next_page=next_page, filters=filters)


@blueprint.route('/decode/<tr_hash>', methods=('GET', 'POST'))
async def decode_xdr(tr_hash):
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
    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        if len(tr_hash) == 64:
            transaction = await repo.get_by_hash(tr_hash)
        else:
            transaction = await repo.get_by_uuid(tr_hash)
    
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
        async with current_app.db_pool() as db_session:
            repo = TransactionRepository(db_session)
            if len(tr_hash) == 64:
                transaction = await repo.get_by_hash(tr_hash)
            else:
                transaction = await repo.get_by_uuid(tr_hash)

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

        if uri and len(uri) > MAX_SEP07_URI_LENGTH:
            message = 'URI слишком длинный для генерации QR-кода'
            logger.warning(f'SEP-07 URI too long for QR (length={len(uri)}). tr_hash={tr_hash}')
            return jsonify({
                'success': False,
                'message': message,
                'file': '',
                'uri': uri
            })

        # Создаем QR-код
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

    # if not await check_user_in_sign(tr_hash):
    #     return jsonify({'success': False, 'message': 'User not found in signers'})

    try:
        async with current_app.db_pool() as db_session:
            result = await db_session.execute(select(Alerts).filter(Alerts.transaction_hash == tr_hash,
                                                    Alerts.tg_id == tg_id))
            alert = result.scalars().first()
            if alert is None:
                alert = Alerts(tg_id=tg_id, transaction_hash=tr_hash)
                db_session.add(alert)
                await db_session.commit()
                return jsonify({
                    'success': True,
                    'icon': 'ti-bell-ringing',
                    'message': 'Alert added successfully'
                })
            else:
                await db_session.delete(alert)
                await db_session.commit()
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
    async with current_app.db_pool() as db_session:
        result = await db_session.execute(select(Alerts).filter(Alerts.transaction_hash == tr_hash))
        alert_query = result.scalars().all()
        for alert in alert_query:
            await skynet_bot.send_message(chat_id=alert.tg_id, text=text, disable_web_page_preview=True, parse_mode='HTML')


if __name__ == '__main__':
    x9dr = 'AA'
    # r = asyncio.run(parse_xdr_for_signatures(xdr))
