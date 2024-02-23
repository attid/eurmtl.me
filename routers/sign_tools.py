import asyncio
import json
from random import random, shuffle
import jsonpickle
import requests
from datetime import datetime

from quart import Markup
from quart import Blueprint, request, render_template, flash, session, redirect, abort
from sqlalchemy import func
from stellar_sdk import DecoratedSignature
from stellar_sdk import Keypair
from stellar_sdk import Network, TransactionEnvelope
from stellar_sdk.exceptions import BadSignatureError
from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr

from db.models import Transactions, Signers, Signatures, Alerts
from db.pool import db_pool
from utils.stellar_utils import decode_xdr_to_text, decode_xdr_to_base64, check_publish_state, check_user_weight
from utils.telegram_utils import send_telegram_message

blueprint = Blueprint('sign_rtools', __name__)


@blueprint.route('/adduser', methods=('GET', 'POST'))
@blueprint.route('/add_user', methods=('GET', 'POST'))
async def start_adduser():
    if request.method == 'POST':
        form_data = await request.form
        username = form_data['username']
        public_key = form_data.get('public_key')
        if len(username) < 3:
            await flash('Need more username')
            resp = await render_template('adduser.html', username=username, public_key=public_key)
            return resp

        if username[0] != '@':
            await flash('Username must start with @')
            resp = await render_template('adduser.html', username=username, public_key=public_key)
            return resp

        if len(public_key) < 56 or public_key[0] != 'G':
            await flash('BAD public key')
            resp = await render_template('adduser.html', username=username, public_key=public_key)
            return resp

        try:
            key = Keypair.from_public_key(public_key)
        except:
            await flash('BAD public key')
            resp = await render_template('adduser.html', username=username, public_key=public_key)
            return resp

        if (await check_user_weight()) > 0:
            with db_pool() as db_session:
                address = db_session.query(Signers).filter(Signers.username == username).first()
                if address:
                    await flash('Username already in use')
                    resp = await render_template('adduser.html', username=username, public_key=public_key)
                    return resp

                address = db_session.query(Signers).filter(Signers.public_key == public_key).first()
                if address:
                    await flash(f'{address.username} was renamed to {username}')
                    address.username = username
                    db_session.commit()
                    resp = await render_template('adduser.html', username=username, public_key=public_key)
                    return resp

                db_session.add(
                    Signers(username=username, public_key=public_key, signature_hint=key.signature_hint().hex()))
                db_session.commit()

                await flash(f'{username} with key {public_key} was added')
                resp = await render_template('adduser.html', username=username, public_key=public_key)
                return resp

    resp = await render_template('adduser.html', username='', public_key='')
    return resp


@blueprint.route('/sign_tools', methods=('GET', 'POST'))
@blueprint.route('/sign_tools/', methods=('GET', 'POST'))
async def start_add_transaction():
    session['return_to'] = request.url
    if request.method == 'POST':
        form_data = await request.form
        use_memo = 'use_memo' in form_data  # Проверка, был ли отмечен checkbox
        tx_body = form_data.get('tx_body')

        # Определение описания на основе выбора пользователя
        if use_memo:
            tx_description = form_data.get('tx_memo')
        else:
            tx_description = form_data.get('tx_description')

        # Проверка длины описания
        if not tx_description or len(tx_description) < 5:
            await flash('Need more description')
            return await render_template('sign_add.html', tx_description=tx_description, tx_body=tx_body)

        try:
            tr = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            tr_full = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            sources = extract_sources(tx_body)
        except:
            await flash('BAD xdr. Can`t load')
            resp = await render_template('sign_add.html', tx_description=tx_description, tx_body=tx_body)
            return resp
        tx_hash = tr.hash_hex()
        tr.signatures.clear()

        with db_pool() as db_session:
            if db_session.query(Transactions).filter(Transactions.hash == tx_hash).first():
                return redirect(f'/sign_tools/{tx_hash}')

            db_session.add(
                Transactions(hash=tx_hash, body=tr.to_xdr(), description=tx_description, json=json.dumps(sources)))
            if len(tr_full.signatures) > 0:
                for signature in tr_full.signatures:
                    signer = db_session.query(Signers).filter(
                        Signers.signature_hint == signature.signature_hint.hex()).first()
                    db_session.add(Signatures(signature_xdr=signature.to_xdr_object().to_xdr(),
                                              signer_id=signer.id if signer else None,
                                              transaction_hash=tx_hash))
            db_session.commit()

        return redirect(f'/sign_tools/{tx_hash}')

    resp = await render_template('sign_add.html', tx_description='', tx_body='')
    return resp


def extract_sources(xdr):
    tr = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    sources = {tr.transaction.source.account_id: {}}
    for operation in tr.transaction.operations:
        if operation.source:
            sources[operation.source.account_id] = {}
    for source in sources:
        try:
            rq = requests.get('https://horizon.stellar.org/accounts/' + source)
            threshold = rq.json()['thresholds']['high_threshold']
            signers = []
            for signer in rq.json()['signers']:
                signers.append([signer['key'], signer['weight'],
                                Keypair.from_public_key(signer['key']).signature_hint().hex()])
                add_signer(signer['key'])
            sources[source] = {'threshold': threshold, 'signers': signers}
        except:
            sources[source] = {'threshold': 0,
                               'signers': [[source, 1, Keypair.from_public_key(source).signature_hint().hex()]]}
            add_signer(source)
    # print(json.dumps(sources))
    return sources


def add_signer(signer):
    with db_pool() as db_session:
        db_signer = db_session.query(Signers).filter(Signers.public_key == signer).first()
        if db_signer is None:
            hint = Keypair.from_public_key(signer).signature_hint().hex()
            db_session.add(Signers(username='FaceLess', public_key=signer,
                                   signature_hint=hint))
            db_session.commit()


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

    admin_weight = await check_user_weight(need_flash=False)
    if admin_weight > 0:
        tg_id = session['userdata']['id']

        with db_pool() as db_session:
            alert = db_session.query(Alerts).filter(Alerts.transaction_hash == tr_hash,
                                                    Alerts.tg_id == tg_id).first()
    else:
        alert = None

    try:
        json_transaction = json.loads(transaction.json)
    except:
        await flash('BAD xdr. Can`t load')
        resp = await render_template('sign_add.html', tx_description='', tx_body='')
        return resp

    if request.method == 'POST':
        form_data = await request.form
        tx_body = form_data.get('tx_body') or form_data.get('xdr')
        # Вызов функции parse_xdr_for_signatures и ожидание её результата
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
                    Signatures.transaction_hash == transaction.hash, Signers.public_key == signer[0]).first()
                db_signer = db_session.query(Signers).filter(Signers.public_key == signer[0]).first()
                signature_dt = db_session.query(Signatures).join(Signers, Signatures.signer_id == Signers.id).filter(
                    Signers.public_key == signer[0]).order_by(Signatures.add_dt.desc()).first()
                username = db_signer.username if db_signer else None
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
            signer = db_session.query(Signers).filter(
                Signers.id == signature.signer_id).first()
            username = signer.username if signer else None
            signatures.append([signature.id, signature.add_dt, username, signature.signature_xdr])
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

                        failed_operation_dict = '<br>'.join(decode_xdr_to_text(transaction.body, only_op_number=i))
                        await flash(Markup(f'Details of failed operation: {failed_operation_dict}'))

                        break

        except Exception as e:
            await flash("Failed to send. The error is unclear")
            await flash(f'{e}')

    resp = await render_template('sign_sign.html', tx_description=transaction.description,
                                 tx_body=transaction.body, tx_hash=transaction.hash,
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
                signer = db_session.query(Signers).filter(
                    Signers.signature_hint == signature.signature_hint.hex()).first()
                if db_session.query(Signatures).filter(Signatures.transaction_hash == transaction.hash,
                                                       Signatures.signature_xdr == signature.to_xdr_object(
                                                       ).to_xdr()).first():
                    result['MESSAGES'].append(f'Can`t add {signer.username if signer else None}. '
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
                            text = f'Added signature from {signer.username if signer else None}'
                            result['MESSAGES'].append(text)
                            result['SUCCESS'] = True
                            alert_singers(tr_hash=transaction.hash, small_text=text,
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

        return await render_template('sign_all.html', transactions=transactions, next_page=next_page)


@blueprint.route('/edit_xdr/<tr_hash>', methods=('GET', 'POST'))
async def edit_xdr(tr_hash):
    session['return_to'] = request.url
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        abort(404)

    with db_pool() as db_session:
        if len(tr_hash) == 64:
            transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
        else:
            transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()

    if transaction is None:
        return 'Transaction not exist =('

    encoded_xdr = decode_xdr_to_base64(transaction.body)
    link = f'https://laboratory.stellar.org/#txbuilder?params={encoded_xdr}&network=public'

    resp = await render_template('edit_xdr.html', tx_body=link)
    return resp


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

    encoded_xdr = decode_xdr_to_text(transaction.body)

    # resp = await make_response(render_template('edit_xdr.html', tx_body=link))
    return ('<br>'.join(encoded_xdr) + '<br><br><br>').replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')


@blueprint.route('/add_alert/<tr_hash>', methods=('GET', 'POST'))
async def add_alert(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        abort(404)

    if (await check_user_weight()) == 0:
        abort(404)

    tg_id = session['userdata']['id']

    with db_pool() as db_session:
        alert = db_session.query(Alerts).filter(Alerts.transaction_hash == tr_hash,
                                                Alerts.tg_id == tg_id).first()
        if alert is None:
            alert = Alerts(tg_id=tg_id, transaction_hash=tr_hash)
            db_session.add(alert)
            db_session.commit()
            return '[+] Alert me'
        else:
            db_session.delete(alert)
            db_session.commit()
            return '[ ] Alert me'


def alert_singers(tr_hash, small_text, tx_description):
    text = (f'Transaction <a href="https://eurmtl.me/sign_tools/{tr_hash}">{tx_description}</a> : '
            f'{small_text}.')
    with db_pool() as db_session:
        alert_query = db_session.query(Alerts).filter(Alerts.transaction_hash == tr_hash).all()
        for alert in alert_query:
            send_telegram_message(alert.tg_id, text)


if __name__ == '__main__':
    xdr = 'AA'
    # r = asyncio.run(parse_xdr_for_signatures(xdr))
    print(extract_sources(xdr))
