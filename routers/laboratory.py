import asyncio

import requests
from flask import Blueprint, render_template, jsonify, request
from stellar_sdk import Server, TransactionBuilder, Network, Asset

from config_reader import config
from db.pool import db_pool
from db.requests import db_get_dict, EURMTLDictsType, db_save_dict
from utils import decode_data_value

blueprint = Blueprint('laboratory', __name__)


@blueprint.route('/laboratory')
def cmd_laboratory():
    return render_template('laboratory.html')


@blueprint.route('/mtl_accounts', methods=['GET', 'POST'])
def cmd_mtl_accounts():
    if request.method == 'POST':
        api_key = request.headers.get('Authorization')
        if api_key != f"Bearer {config.eurmtl_key}":
            return jsonify({"message": "Unauthorized"}), 401

        data = request.json
        if not data or not isinstance(data, dict):
            return jsonify({"message": "Invalid data"}), 400

        db_save_dict(db_pool(), EURMTLDictsType.Accounts, data)
        return jsonify({"message": "Success"})

    elif request.method == 'GET':
        result = db_get_dict(db_pool(), EURMTLDictsType.Accounts)
        return jsonify(result)


@blueprint.route('/sequence/<account_id>')
def cmd_sequence(account_id):
    try:
        r = requests.get('https://horizon.stellar.org/accounts/' + account_id).json()
        sequence = int(r['sequence']) + 1
    except:
        sequence = 0
    return jsonify({'sequence': str(sequence)})


@blueprint.route('/mtl_assets', methods=['GET', 'POST'])
def cmd_mtl_assets():
    if request.method == 'POST':
        api_key = request.headers.get('Authorization')
        if api_key != f"Bearer {config.eurmtl_key}":
            return jsonify({"message": "Unauthorized"}), 401

        data = request.json
        if not data or not isinstance(data, dict):
            return jsonify({"message": "Invalid data"}), 400

        db_save_dict(db_pool(), EURMTLDictsType.Assets, data)
        return jsonify({"message": "Success"})

    elif request.method == 'GET':
        result = db_get_dict(db_pool(), EURMTLDictsType.Assets)
        result["XLM"] = "XLM"
        return jsonify(result)


def decode_asset(asset):
    arr = asset.split('-')
    if arr[0] == 'XLM':
        return Asset(arr[0])
    else:
        return Asset(arr[0], arr[1])


@blueprint.route('/build_xdr', methods=['POST'])
def cmd_build_xdr():
    data = request.json
    # {'publicKey': 'GAUBJ4CTRF42Z7OM7QXTAQZG6BEMNR3JZY57Z4LB3PXSDJXE5A5GIGJB', 'sequence': '167193185523597322', 'memo_type': 'text', 'memo': '654654',
    # 'operations': [{'type': 'payment', 'destination': 'GBTOF6RLHRPG5NRIU6MQ7JGMCV7YHL5V33YYC76YYG4JUKCJTUP5DEFI', 'asset': 'Agora-GBGGX7QD3JCPFKOJTLBRAFU3SIME3WSNDXETWI63EDCORLBB6HIP2CRR', 'amount': '66', 'sourceAccount': ''}]}

    root_account = Server(horizon_url="https://horizon.stellar.org").load_account(data['publicKey'])
    transaction = TransactionBuilder(source_account=root_account, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                                     base_fee=10101)
    transaction.set_timeout(60 * 60 * 24 * 7)
    if data['memo_type'] == 'text':
        transaction.add_text_memo(data['memo'])
    if data['memo_type'] == 'hash':
        transaction.add_hash_memo(data['memo'])

    for operation in data['operations']:
        sourceAccount = operation['sourceAccount'] if len(operation['sourceAccount']) == 56 else None
        if operation['type'] == 'payment':
            transaction.append_payment_op(destination=operation['destination'],
                                          asset=decode_asset(operation['asset']),
                                          amount=operation['amount'],
                                          source=sourceAccount)
        if operation['type'] == 'change_trust':
            transaction.append_change_trust_op(asset=decode_asset(operation['asset']),
                                               limit=operation['amount'] if len(operation['amount']) > 0 else None,
                                               source=sourceAccount)
        if operation['type'] == 'create_account':
            transaction.append_create_account_op(destination=operation['destination'],
                                                 starting_balance=operation['startingBalance'],
                                                 source=sourceAccount)
        if operation['type'] == 'sell':
            transaction.append_manage_sell_offer_op(selling=decode_asset(operation['selling']),
                                                    buying=decode_asset(operation['buying']),
                                                    amount=operation['amount'],
                                                    price=operation['price'],
                                                    offer_id=int(operation['offer_id']),
                                                    source=sourceAccount)
        if operation['type'] == 'buy':
            transaction.append_manage_buy_offer_op(selling=decode_asset(operation['selling']),
                                                   buying=decode_asset(operation['buying']),
                                                   amount=operation['amount'],
                                                   price=operation['price'],
                                                   offer_id=int(operation['offer_id']),
                                                   source=sourceAccount)
        if operation['type'] == 'manage_data':
            transaction.append_manage_data_op(data_name=operation['data_name'],
                                              data_value=operation['data_value'] if len(
                                                  operation['data_value']) > 0 else None,
                                              source=sourceAccount)

    transaction = transaction.build()
    transaction.transaction.sequence = int(data['sequence'])
    xdr = transaction.to_xdr()

    return jsonify({'xdr': xdr})


@blueprint.route('/assets/<account_id>')
def cmd_assets(account_id):
    result = {'XLM': 'XLM'}
    try:
        account = Server(horizon_url="https://horizon.stellar.org").accounts().account_id(account_id).call()
        for balance in account['balances']:
            result[balance.get('asset_code', 'XLM')] = balance.get('asset_issuer', 'XLM')
        assets = Server(horizon_url="https://horizon.stellar.org").assets().for_issuer(account_id).call()
        for asset in assets['_embedded']['records']:
            result[asset.get('asset_code', 'XLM')] = asset.get('asset_issuer', 'XLM')
    except:
        pass

    return jsonify(result)


@blueprint.route('/data/<account_id>')
def cmd_data(account_id):
    result = {}
    try:
        account = Server(horizon_url="https://horizon.stellar.org").accounts().account_id(account_id).call()
        for data_name in account.get('data'):
            result[data_name] = decode_data_value(account['data'][data_name])
    except:
        pass
    result['mtl_delegate'] = 'if you want delegate your mtl votes'
    result['mtl_donate'] = 'if you want donate'
    print(result)
    return jsonify(result)


if __name__ == '__main__':
    cmd_data('GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V')
