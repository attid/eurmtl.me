import uuid
from datetime import datetime
from flask import render_template, request, jsonify, make_response, send_file, flash, abort, redirect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from stellar_sdk import Keypair
from stellar_sdk.exceptions import BadSignatureError
from stellar_sdk import DecoratedSignature
from stellar_sdk.xdr import DecoratedSignature as DecoratedSignatureXdr
from config_reader import config
from db.models import Addresses, Transactions, Signers, Signatures, Base
from utils import *
from flask import Flask

app = Flask(__name__)
app.config['SECRET_KEY'] = config.secret_key
# app.config['HOME_PATH'] = ''
# app.config['TELEGRAM_BOT_TOKEN'] = '5'
engine = create_engine(
    config.db_dns,
    pool_pre_ping=True,
    pool_size=10,  # базовый размер пула
    max_overflow=50,  # максимальное количество "временных" подключений
    pool_timeout=10  # время ожидания в секундах
)  # Creating DB connections pool
db_pool = sessionmaker(bind=engine)

fund_addresses = ('GDX23CPGMQ4LN55VGEDVFZPAJMAUEHSHAMJ2GMCU2ZSHN5QF4TMZYPIS',
                  'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V')


# locale.setlocale(locale.LC_ALL, 'en_GB.UTF-8')


@app.route('/')
def index():
    text = 'This is a technical domain montelibero.org. ' \
           'You can get more information on the website <a href="https://montelibero.org">montelibero.org</a> ' \
           'or in telegram <a href="https://t.me/Montelibero_org">Montelibero_org</a>' \
           '<br><br><br>' \
           'Это технический домен montelibero.org. ' \
           'Больше информации вы можете получить на сайте <a href="https://montelibero.org">montelibero.org</a> ' \
           'или в телеграм <a href="https://t.me/Montelibero_ru">Montelibero_ru</a>'
    return text


@app.route('/mytest', methods=('GET', 'POST'))
def mytest():
    return '''
    <body>
        <script async src="https://telegram.org/js/telegram-widget.js?21" 
            data-telegram-login="MyMTLWalletBot" 
            data-size="small" 
            data-auth-url="https://eurmtl.me/login/telegram" 
            data-request-access="write">
        </script>
    </body>    
    '''


@app.route('/uuid', methods=('GET', 'POST'))
def get_uuid():
    return uuid.uuid4().hex


@app.route('/federation')
@app.route('/federation/')
def federation():
    # https://eurmtl.me/federation/?q=english*eurmtl.me&type=name
    # https://eurmtl.me/federation/?q=GAPQ3YSV4IXUC2MWSVVUHGETWE6C2OYVFTHM3QFBC64MQWUUIM5PCLUB&type=id
    if request.args.get('q') and request.args.get('type'):
        if request.args.get('type') == 'name':
            with db_pool() as db_session:
                address = db_session.query(Addresses).filter(Addresses.stellar_address == request.args.get('q')).first()
                if address:
                    result = {"stellar_address": address.stellar_address,
                              "account_id": address.account_id}
                    if address.memo:
                        result['memo_type'] = "text"
                        result['memo'] = address.memo
                    resp = jsonify(result)
                    resp.headers.add('Access-Control-Allow-Origin', '*')
                    return resp

        if request.args.get('type') == 'id':
            with db_pool() as db_session:
                address = db_session.query(Addresses).filter(Addresses.account_id == request.args.get('q')).first()
                if address:
                    result = {"stellar_address": address.stellar_address,
                              "account_id": address.account_id}
                    resp = jsonify(result)
                    resp.headers.add('Access-Control-Allow-Origin', '*')
                    return resp

    return jsonify({'error': "Not found."})


@app.route('/.well-known/stellar.toml')
def stellar_toml():
    resp = make_response(render_template('stellar.toml'))
    resp.headers.add('Access-Control-Allow-Origin', '*')
    resp.headers.add('Content-Type', 'text/plain')
    return resp


@app.route('/updatedb')
def update_db():
    # Base.metadata.drop_all(engine, tables=[Signatures])
    # DROP TABLE ` t_signatures `
    # session.execute('DROP TABLE t_signatures')
    # session.execute('DROP TABLE t_transactions')
    # session.execute('DROP TABLE t_signers')
    # session.commit()
    Base.metadata.create_all(engine)
    return "OK"


@app.route('/err', methods=('GET', 'POST'))
def send_err():
    debug = True
    if debug:
        file_name = '/home/c/cb61047/eurmtl.me/error_log'
        import os
        if os.path.isfile(file_name):
            return send_file(file_name, mimetype='text/plain')
            # with open(file_name, "r") as f:
            #    text = f.read()
        else:
            return "No error"
    else:
        return "need authority"


@app.route('/adduser', methods=('GET', 'POST'))
def start_adduser():
    if request.method == 'POST':
        username = request.form['username']
        public_key = request.form.get('public_key')
        if len(username) < 3:
            flash('Need more username')
            resp = make_response(render_template('adduser.html', username=username, public_key=public_key))
            return resp

        if username[0] != '@':
            flash('Username must start with @')
            resp = make_response(render_template('adduser.html', username=username, public_key=public_key))
            return resp

        if len(public_key) < 56 or public_key[0] != 'G':
            flash('BAD public key')
            resp = make_response(render_template('adduser.html', username=username, public_key=public_key))
            return resp

        try:
            key = Keypair.from_public_key(public_key)
        except:
            flash('BAD public key')
            resp = make_response(render_template('adduser.html', username=username, public_key=public_key))
            return resp

        with db_pool() as db_session:
            address = db_session.query(Signers).filter(Signers.public_key == public_key).first()
            if address:
                if address.username == 'FaceLess':
                    flash('FaceLess was renamed')
                    address.username = username
                    db_session.commit()
                else:
                    flash('Public key already in use')
                resp = make_response(render_template('adduser.html', username=username, public_key=public_key))
                return resp

            address = db_session.query(Signers).filter(Signers.username == username).first()
            if address:
                flash('Username already in use')
                resp = make_response(render_template('adduser.html', username=username, public_key=public_key))
                return resp

            db_session.add(Signers(username=username, public_key=public_key, signature_hint=key.signature_hint().hex()))
            db_session.commit()

            flash(f'{username} with key {public_key} was added')
            resp = make_response(render_template('adduser.html', username=username, public_key=public_key))
            return resp

    resp = make_response(render_template('adduser.html', username='', public_key=''))
    return resp


@app.route('/sign_tools', methods=('GET', 'POST'))
@app.route('/sign_tools/', methods=('GET', 'POST'))
def start_add_transaction():
    if request.method == 'POST':
        tx_description = request.form['tx_description']
        tx_body = request.form.get('tx_body')
        if len(tx_description) < 5:
            flash('Need more description')
            resp = make_response(render_template('sign_add.html', tx_description=tx_description, tx_body=tx_body))
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
                sources[source] = {'threshold': threshold, 'signers': signers}
            # print(json.dumps(sources))

        except:
            flash('BAD xdr. Can`t load')
            resp = make_response(render_template('sign_add.html', tx_description=tx_description, tx_body=tx_body))
            return resp
        tx_hash = tr.hash_hex()
        tr.signatures.clear()

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

    resp = make_response(render_template('sign_add.html', tx_description='', tx_body=''))
    return resp


@app.route('/sign_tools/<tr_hash>', methods=('GET', 'POST'))
def show_transaction(tr_hash):
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
        flash('BAD xdr. Can`t load')
        resp = make_response(render_template('sign_add.html', tx_description='', tx_body=''))
        return resp

    if request.method == 'POST':
        tx_body = request.form.get('tx_body')
        try:
            tr_full = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
            if tr_full.hash_hex() != transaction.hash:
                flash('Not same xdr =(')
            else:
                if len(tr_full.signatures) > 0:
                    with db_pool() as db_session:

                        for signature in tr_full.signatures:
                            signer = db_session.query(Signers).filter(
                                Signers.signature_hint == signature.signature_hint.hex()).first()
                            if db_session.query(Signatures).filter(Signatures.transaction_hash == transaction.hash,
                                                                   Signatures.signature_xdr == signature.to_xdr_object(
                                                                   ).to_xdr()).first():
                                flash(f'Can`t add {signer.username if signer else None}. Already was add.', 'good')
                            else:
                                # check is good ?
                                all_sign = []
                                for record in json_transaction:
                                    all_sign.extend(json_transaction[record]['signers'])
                                json_signer = list(filter(lambda x: x[2] == signature.signature_hint.hex(), all_sign))
                                if len(json_signer) == 0:
                                    flash(f'Bad signature. {signature.signature_hint.hex()} not found')
                                else:
                                    user_keypair = Keypair.from_public_key(json_signer[0][0])
                                    try:
                                        user_keypair.verify(data=transaction_env.hash(), signature=signature.signature)
                                        db_session.add(Signatures(signature_xdr=signature.to_xdr_object().to_xdr(),
                                                                  signer_id=signer.id if signer else None,
                                                                  transaction_hash=transaction.hash))
                                        flash(f'Added signature from {signer.username if signer else None}', 'good')
                                    except BadSignatureError:
                                        flash(f'Bad signature. {signature.signature_hint.hex()} not verify')
                        db_session.commit()
        except:
            flash(f'BAD xdr. Can`t load ')

    signers_table = []
    bad_signers = []
    signatures = []
    for address in json_transaction:
        signers = []
        has_votes = 0
        # find bad signer and calc votes
        for signer in json_transaction[address]['signers']:
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
                    # flash(json_transaction[address]['threshold'], 'good')
                    signature_xdr = DecoratedSignature.from_xdr_object(
                        DecoratedSignatureXdr.from_xdr(signature.signature_xdr))
                    if signature_xdr in transaction_env.signatures:
                        pass
                    else:
                        transaction_env.signatures.append(signature_xdr)
                        # flash(f'*{address} need {json_transaction[address]["threshold"]} {has_votes} Added signature from {username} {signer[1]}', 'good')
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
    # flash(transaction.json)

    # try send
    send = request.args.get('send', default=None)
    if send is not None:
        try:
            transaction_resp = requests.post('https://horizon.stellar.org/transactions/',
                                             data={"tx": transaction_env.to_xdr()})
            if transaction_resp.status_code == 200:
                flash(f'Successfully sent, accepted : {transaction_resp.json()["successful"]}', 'good')
            else:
                flash(f'Failed to send. {transaction_resp.json()["extras"]["result_codes"]}')
        except Exception as e:
            flash("Failed to send. The error is unclear")
            flash(f'{e}')

    resp = make_response(render_template('sign_sign.html', tx_description=transaction.description,
                                         tx_body=transaction.body, tx_hash=transaction.hash,
                                         bad_signers=set(bad_signers), signatures=signatures,
                                         signers_table=signers_table, uuid=transaction.uuid,
                                         tx_full=transaction_env.to_xdr(),
                                         publish_state=check_publish_state(transaction.hash)))
    return resp


@app.route('/sign_all', methods=('GET', 'POST'))
@app.route('/sign_all/', methods=('GET', 'POST'))
def start_show_all_transactions():
    with db_pool() as db_session:
        transactions = db_session.query(Transactions).order_by(Transactions.add_dt.desc()).all()
        resp = make_response(render_template('sign_all.html', transactions=transactions))
        return resp


@app.route('/edit_xdr/<tr_hash>', methods=('GET', 'POST'))
def edit_xdr(tr_hash):
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

    resp = make_response(render_template('edit_xdr.html', tx_body=link))
    return resp


@app.route('/decode/<tr_hash>', methods=('GET', 'POST'))
def decode_xdr(tr_hash):
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

    # resp = make_response(render_template('edit_xdr.html', tx_body=link))
    return ('<br>'.join(encoded_xdr) + '<br><br><br>').replace('\n', '<br>').replace('  ', '&nbsp;&nbsp;')


@app.route('/login/telegram')
def login_telegram():
    data = {
        'id': request.args.get('id', None),
        'first_name': request.args.get('first_name', None),
        'last_name': request.args.get('last_name', None),
        'username': request.args.get('username', None),
        'photo_url': request.args.get('photo_url', None),
        'auth_date': request.args.get('auth_date', None),
        'hash': request.args.get('hash', None)
    }

    if check_response(data):
        # Authorize user
        return data
    else:
        return 'Authorization failed'


@app.route('/mmwb')
def mmwb_tools():
    return render_template('mmwb_tools.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
