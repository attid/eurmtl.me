import json
import requests
from datetime import datetime
from quart import Blueprint, request, make_response, render_template, flash, session, redirect, abort
from stellar_sdk import Network, TransactionEnvelope
from stellar_sdk import Keypair
from stellar_sdk.exceptions import BadSignatureError
from stellar_sdk import DecoratedSignature
from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
from db.models import Transactions, Signers, Signatures
from db.pool import db_pool
from utils import decode_xdr_to_text, decode_xdr_to_base64, check_publish_state, check_response

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

        with db_pool() as db_session:
            address = db_session.query(Signers).filter(Signers.username == username).first()
            if address:
                await flash('Username already in use')
                resp = await render_template('adduser.html', username=username, public_key=public_key)
                return resp

            address = db_session.query(Signers).filter(Signers.public_key == public_key).first()
            if address:
                if address.username == 'FaceLess':
                    await flash('FaceLess was renamed')
                    address.username = username
                    db_session.commit()
                else:
                    await flash('Public key already in use')
                resp = await render_template('adduser.html', username=username, public_key=public_key)
                return resp


            db_session.add(Signers(username=username, public_key=public_key, signature_hint=key.signature_hint().hex()))
            db_session.commit()

            await flash(f'{username} with key {public_key} was added')
            resp = await render_template('adduser.html', username=username, public_key=public_key)
            return resp

    resp = await render_template('adduser.html', username='', public_key='')
    return resp


@blueprint.route('/sign_tools', methods=('GET', 'POST'))
@blueprint.route('/sign_tools/', methods=('GET', 'POST'))
async def start_add_transaction():
    if request.method == 'POST':
        form_data = await request.form
        tx_description = form_data['tx_description']
        tx_body = form_data.get('tx_body')
        if len(tx_description) < 5:
            await flash('Need more description')
            resp = await render_template('sign_add.html', tx_description=tx_description, tx_body=tx_body)
            return resp

        try:
            tr = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            tr_full = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            sources = {tr.transaction.source.account_id: {}}
            for operation in tr.transaction.operations:
                if operation.source:
                    sources[operation.source.account_id] = {}
            for source in sources:
                rq = requests.get('https://horizon.stellar.org/accounts/' + source)
                threshold = rq.json()['thresholds']['high_threshold']
                signers = []
                for signer in rq.json()['signers']:
                    signers.append([signer['key'], signer['weight'],
                                    Keypair.from_public_key(signer['key']).signature_hint().hex()])
                    with db_pool() as db_session:
                        db_signer = db_session.query(Signers).filter(Signers.public_key == signer['key']).first()
                        if db_signer is None:
                            hint = Keypair.from_public_key(signer['key']).signature_hint().hex()
                            db_session.add(Signers(username='FaceLess', public_key=signer['key'],
                                                   signature_hint=hint))
                            db_session.commit()
                sources[source] = {'threshold': threshold, 'signers': signers}
            # print(json.dumps(sources))

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


@blueprint.route('/sign_tools/<tr_hash>', methods=('GET', 'POST'))
async def show_transaction(tr_hash):
    if len(tr_hash) != 64 and len(tr_hash) != 32:
        abort(404)

    with db_pool() as db_session:
        if len(tr_hash) == 64:
            transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
        else:
            transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()

    if transaction is None:
        return 'Transaction not exist =('

    transaction_env = TransactionEnvelope.from_xdr(transaction.body,
                                                   network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)

    try:
        json_transaction = json.loads(transaction.json)
    except:
        await flash('BAD xdr. Can`t load')
        resp = await render_template('sign_add.html', tx_description='', tx_body='')
        return resp

    if request.method == 'POST':
        form_data = await request.form
        tx_body = form_data.get('tx_body') or form_data.get('xdr')
        try:
            tr_full = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            if tr_full.hash_hex() != transaction.hash:
                await flash('Not same xdr =(')
            else:
                if len(tr_full.signatures) > 0:
                    with db_pool() as db_session:
                        for signature in tr_full.signatures:
                            signer = db_session.query(Signers).filter(
                                Signers.signature_hint == signature.signature_hint.hex()).first()
                            if db_session.query(Signatures).filter(Signatures.transaction_hash == transaction.hash,
                                                                   Signatures.signature_xdr == signature.to_xdr_object(
                                                                   ).to_xdr()).first():
                                await flash(f'Can`t add {signer.username if signer else None}. Already was add.',
                                            'good')
                            else:
                                # check is good ?
                                all_sign = []
                                for record in json_transaction:
                                    all_sign.extend(json_transaction[record]['signers'])
                                json_signer = list(filter(lambda x: x[2] == signature.signature_hint.hex(), all_sign))
                                if len(json_signer) == 0:
                                    await flash(f'Bad signature. {signature.signature_hint.hex()} not found')
                                else:
                                    user_keypair = Keypair.from_public_key(json_signer[0][0])
                                    try:
                                        user_keypair.verify(data=transaction_env.hash(), signature=signature.signature)
                                        db_session.add(Signatures(signature_xdr=signature.to_xdr_object().to_xdr(),
                                                                  signer_id=signer.id if signer else None,
                                                                  transaction_hash=transaction.hash))
                                        await flash(f'Added signature from {signer.username if signer else None}',
                                                    'good')
                                    except BadSignatureError:
                                        await flash(f'Bad signature. {signature.signature_hint.hex()} not verify')
                        db_session.commit()
        except:
            await flash(f'BAD xdr. Can`t load ')

    signers_table = []
    bad_signers = []
    signatures = []
    for address in json_transaction:
        signers = []
        has_votes = 0
        # find bad signer and calc votes
        for signer in json_transaction[address]['signers']:
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
                    if signature_xdr in transaction_env.signatures:
                        pass
                    else:
                        transaction_env.signatures.append(signature_xdr)
                        # await flash(f'*{address} need {json_transaction[address]["threshold"]} {has_votes} Added signature from {username} {signer[1]}', 'good')
                has_votes += signer[1]
                # with suppress(ValueError):
                #    if signature_xdr in transaction_env.signatures.index(signature_xdr):
                #        print('signature_xdr exist')
                #    else:
                #        print('signature_xdr addede')

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
            transaction_resp = requests.post('https://horizon.stellar.org/transactions/',
                                             data={"tx": transaction_env.to_xdr()})
            if transaction_resp.status_code == 200:
                await flash(f'Successfully sent, accepted : {transaction_resp.json()["successful"]}', 'good')
            else:
                await flash(f'Failed to send. {transaction_resp.json()["extras"]["result_codes"]}')
        except Exception as e:
            await flash("Failed to send. The error is unclear")
            await flash(f'{e}')

    # xxx = 'AAAAAgAAAAAEqbejBk1rxsHVls854RnAyfpJaZacvgwmQ0jxNDBvqgABhwQCGVTNAAAESgAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAYzMjE2NTQAAAAAAAEAAAAAAAAABgAAAAFNTU0AAAAAAASpt6MGTWvGwdWWzznhGcDJ+klplpy+DCZDSPE0MG+qf/////////8AAAAAAAAAAA=='
    # qr_text = (f'web+stellar:tx?xdr={quote_plus(xxx)}'
    #            f'&callback={quote_plus(f"https://eurmtl.me/sign_tools/{transaction.hash}")}'
    #            f'&msg={quote_plus(transaction.description[:200])}'
    #            #f'&pubkey=GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI'
    #            f'&origin_domain=eurmtl.me')
    # signature = uri_sign(qr_text, config_reader.config.signing_key.get_secret_value())
    # qr_text = f'{qr_text}&signature={signature}'
    # qr_img = f'/static/qr/{uuid.uuid4().hex}.svg'
    # qr = pyqrcode.create(qr_text)
    # qr.svg(start_path + qr_img, scale=6)

    resp = await render_template('sign_sign.html', tx_description=transaction.description,
                                 tx_body=transaction.body, tx_hash=transaction.hash,
                                 bad_signers=set(bad_signers), signatures=signatures,
                                 signers_table=signers_table, uuid=transaction.uuid,
                                 tx_full=transaction_env.to_xdr(),
                                 publish_state=check_publish_state(transaction.hash))
    return resp


@blueprint.route('/sign_all', methods=('GET', 'POST'))
@blueprint.route('/sign_all/', methods=('GET', 'POST'))
async def start_show_all_transactions():
    with db_pool() as db_session:
        transactions = db_session.query(Transactions).order_by(Transactions.add_dt.desc()).all()
        resp = await render_template('sign_all.html', transactions=transactions)
        return resp


@blueprint.route('/edit_xdr/<tr_hash>', methods=('GET', 'POST'))
async def edit_xdr(tr_hash):
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


@blueprint.route('/login')
async def login_telegram():
    data = {
        'id': request.args.get('id', None),
        'first_name': request.args.get('first_name', None),
        'last_name': request.args.get('last_name', None),
        'username': request.args.get('username', None),
        'photo_url': request.args.get('photo_url', None),
        'auth_date': request.args.get('auth_date', None),
        'hash': request.args.get('hash', None)
    }

    if check_response(data) and data['username']:
        # Authorize user
        session['userdata'] = data
        return redirect('/lab')
    else:
        return 'Authorization failed'


@blueprint.route('/logout')
async def logout():
    await session.pop('userdata', None)
    return redirect('/lab')
