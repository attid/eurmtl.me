from quart import Blueprint, request, jsonify, make_response, render_template
from db.models import Addresses
from db.pool import db_pool

blueprint = Blueprint('federal', __name__)


@blueprint.route('/federation')
@blueprint.route('/federation/')
async def federation():
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


@blueprint.route('/.well-known/stellar.toml')
async def stellar_toml():
    resp = await make_response(await render_template('stellar.toml'))
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Content-Type'] = 'text/plain'
    return resp
