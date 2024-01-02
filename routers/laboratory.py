import asyncio
import json

import requests
from quart import Blueprint, request, render_template, jsonify, session
from stellar_sdk import Server, TransactionBuilder, Network, Asset, TrustLineFlags

from config_reader import config
from db.pool import db_pool
from db.requests import db_get_dict, EURMTLDictsType, db_save_dict
from utils.stellar_utils import decode_data_value, float2str, stellar_copy_multi_sign, decode_xdr_to_base64

blueprint = Blueprint('lab', __name__)


@blueprint.route('/laboratory')
@blueprint.route('/lab')
@blueprint.route('/lab/')
async def cmd_laboratory():
    session['return_to'] = request.url
    return await render_template('laboratory.html')


@blueprint.route('/lab/mtl_accounts', methods=['GET', 'POST'])
async def cmd_mtl_accounts():
    if request.method == 'POST':
        api_key = request.headers.get('Authorization')
        if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
            return jsonify({"message": "Unauthorized"}), 401

        data = await request.json
        if not data or not isinstance(data, dict):
            return jsonify({"message": "Invalid data"}), 400

        db_save_dict(db_pool(), EURMTLDictsType.Accounts, data)
        return jsonify({"message": "Success"})

    elif request.method == 'GET':
        result = {}
        db_data = db_get_dict(db_pool(), EURMTLDictsType.Accounts)
        for asset_code in db_data:
            asset_issuer = db_data[asset_code]
            result[f"{asset_code} {asset_issuer[:4]}..{asset_issuer[-4:]}"] = asset_issuer

        return jsonify(result)


@blueprint.route('/lab/sequence/<account_id>')
async def cmd_sequence(account_id):
    try:
        r = requests.get('https://horizon.stellar.org/accounts/' + account_id).json()
        sequence = int(r['sequence']) + 1
    except:
        sequence = 0
    return jsonify({'sequence': str(sequence)})


@blueprint.route('/lab/mtl_assets', methods=['GET', 'POST'])
async def cmd_mtl_assets():
    if request.method == 'POST':
        api_key = request.headers.get('Authorization')
        if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
            return jsonify({"message": "Unauthorized"}), 401

        data = await request.json
        if not data or not isinstance(data, dict):
            return jsonify({"message": "Invalid data"}), 400

        db_save_dict(db_pool(), EURMTLDictsType.Assets, data)
        return jsonify({"message": "Success"})

    elif request.method == 'GET':
        result = {}
        db_data = db_get_dict(db_pool(), EURMTLDictsType.Assets)
        for asset_code in db_data:
            asset_issuer = db_data[asset_code]
            result[f"{asset_code}-{asset_issuer[:4]}..{asset_issuer[-4:]}"] = f"{asset_code}-{asset_issuer}"

        result["XLM"] = "XLM"
        return jsonify(result)


def decode_asset(asset):
    arr = asset.split('-')
    if arr[0] == 'XLM':
        return Asset(arr[0])
    else:
        return Asset(arr[0], arr[1])


@blueprint.route('/lab/build_xdr', methods=['POST'])
async def cmd_build_xdr():
    data = await request.json
    # {'publicKey': 'GAUBJ4CTRF42Z7OM7QXTAQZG6BEMNR3JZY57Z4LB3PXSDJXE5A5GIGJB', 'sequence': '167193185523597322',
    # 'memo_type': 'text', 'memo': '654654',
    # 'operations': [{'type': 'payment', 'destination': 'GBTOF6RLHRPG5NRIU6MQ7JGMCV7YHL5V33YYC76YYG4JUKCJTUP5DEFI',
    # 'asset': 'Agora-GBGGX7QD3JCPFKOJTLBRAFU3SIME3WSNDXETWI63EDCORLBB6HIP2CRR', 'amount': '66', 'sourceAccount': ''}]}

    root_account = Server(horizon_url="https://horizon.stellar.org").load_account(data['publicKey'])
    transaction = TransactionBuilder(source_account=root_account, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                                     base_fee=10101)
    transaction.set_timeout(60 * 60 * 24 * 7)
    if data['memo_type'] == 'memo_text':
        transaction.add_text_memo(data['memo'])
    if data['memo_type'] == 'memo_hash':
        transaction.add_hash_memo(data['memo'])

    for operation in data['operations']:
        source_account = operation['sourceAccount'] if len(operation['sourceAccount']) == 56 else None
        if operation['type'] == 'payment':
            transaction.append_payment_op(destination=operation['destination'],
                                          asset=decode_asset(operation['asset']),
                                          amount=float2str(operation['amount']),
                                          source=source_account)
        if operation['type'] == 'clawback':
            transaction.append_clawback_op(from_=operation['from'],
                                           asset=decode_asset(operation['asset']),
                                           amount=float2str(operation['amount']),
                                           source=source_account)
        if operation['type'] == 'copy_multi_sign':
            public_key = source_account if source_account else data['publicKey']
            updated_signers = await stellar_copy_multi_sign(public_key_from=operation['from'],
                                                            public_key_for=public_key)
            for signer in updated_signers:
                if signer['key'] == public_key:
                    transaction.append_set_options_op(master_weight=signer['weight'],
                                                      source=source_account)
                elif signer['key'] == 'threshold':
                    transaction.append_set_options_op(med_threshold=signer['med_threshold'],
                                                      low_threshold=signer['low_threshold'],
                                                      high_threshold=signer['high_threshold'],
                                                      source=source_account)
                else:
                    transaction.append_ed25519_public_key_signer(account_id=signer['key'],
                                                                 weight=signer['weight'],
                                                                 source=source_account)
        if operation['type'] == 'trust_payment':
            transaction.append_set_trust_line_flags_op(trustor=operation['destination'],
                                                       asset=decode_asset(operation['asset']),
                                                       set_flags=TrustLineFlags.AUTHORIZED_FLAG,
                                                       source=source_account)
            transaction.append_payment_op(destination=operation['destination'],
                                          asset=decode_asset(operation['asset']),
                                          amount=float2str(operation['amount']),
                                          source=source_account)
            transaction.append_set_trust_line_flags_op(trustor=operation['destination'],
                                                       asset=decode_asset(operation['asset']),
                                                       clear_flags=TrustLineFlags.AUTHORIZED_FLAG,
                                                       source=source_account)
        if operation['type'] == 'change_trust':
            transaction.append_change_trust_op(asset=decode_asset(operation['asset']),
                                               limit=operation['amount'] if len(operation['amount']) > 0 else None,
                                               source=source_account)
        if operation['type'] == 'create_account':
            transaction.append_create_account_op(destination=operation['destination'],
                                                 starting_balance=operation['startingBalance'],
                                                 source=source_account)
        if operation['type'] == 'sell':
            transaction.append_manage_sell_offer_op(selling=decode_asset(operation['selling']),
                                                    buying=decode_asset(operation['buying']),
                                                    amount=float2str(operation['amount']),
                                                    price=float2str(operation['price']),
                                                    offer_id=int(operation['offer_id']),
                                                    source=source_account)
        if operation['type'] == 'swap':
            asset_path = []
            for asset in json.loads(operation['path']):
                asset_path.append(decode_asset(f'{asset["asset_code"]}-{asset["asset_issuer"]}'))
            transaction.append_path_payment_strict_send_op(path=asset_path,
                                                           destination=source_account if source_account else data[
                                                               'publicKey'],
                                                           send_asset=decode_asset(operation['selling']),
                                                           dest_asset=decode_asset(operation['buying']),
                                                           send_amount=float2str(operation['amount']),
                                                           dest_min=float2str(operation['destination']),

                                                           source=source_account)
        if operation['type'] == 'sell_passive':
            transaction.append_create_passive_sell_offer_op(selling=decode_asset(operation['selling']),
                                                            buying=decode_asset(operation['buying']),
                                                            amount=float2str(operation['amount']),
                                                            price=float2str(operation['price']),
                                                            source=source_account)
        if operation['type'] == 'buy':
            transaction.append_manage_buy_offer_op(selling=decode_asset(operation['selling']),
                                                   buying=decode_asset(operation['buying']),
                                                   amount=float2str(operation['amount']),
                                                   price=float2str(operation['price']),
                                                   offer_id=int(operation['offer_id']),
                                                   source=source_account)
        if operation['type'] == 'manage_data':
            transaction.append_manage_data_op(data_name=operation['data_name'],
                                              data_value=operation['data_value'] if len(
                                                  operation['data_value']) > 0 else None,
                                              source=source_account)
        if operation['type'] == 'options':
            transaction.append_set_options_op(
                master_weight=int(operation['master']) if len(operation['master']) > 0 else None,
                med_threshold=int(operation['threshold']) if len(operation['threshold']) > 0 else None,
                high_threshold=int(operation['threshold']) if len(operation['threshold']) > 0 else None,
                low_threshold=int(operation['threshold']) if len(operation['threshold']) > 0 else None,
                home_domain=operation['home'] if len(operation['home']) > 0 else None,
                source=source_account)
        if operation['type'] == 'options_signer':
            transaction.append_ed25519_public_key_signer(
                account_id=operation['signerAccount'] if len(operation['signerAccount']) > 55 else None,
                weight=int(operation['weight']) if len(operation['weight']) > 0 else None,
                source=source_account)

    transaction = transaction.build()
    # transaction.transaction.sequence = int(data['sequence'])
    xdr = transaction.to_xdr()

    return jsonify({'xdr': xdr})


@blueprint.route('/lab/xdr_to_json', methods=['POST'])
async def cmd_xdr_to_json():
    data = await request.json
    xdr = data.get("xdr")
    result = decode_xdr_to_base64(xdr, return_json=True)
    return jsonify(result)


@blueprint.route('/lab/assets/<account_id>')
async def cmd_assets(account_id):
    result = {'XLM': 'XLM'}
    try:
        account = Server(horizon_url="https://horizon.stellar.org").accounts().account_id(account_id).call()
        for balance in account['balances']:
            asset_code = balance.get('asset_code', 'XLM')
            asset_issuer = balance.get('asset_issuer', 'XLM')
            result[f"{asset_code}-{asset_issuer[:4]}..{asset_issuer[-4:]}"] = f"{asset_code}-{asset_issuer}"
        assets = Server(horizon_url="https://horizon.stellar.org").assets().for_issuer(account_id).call()
        for asset in assets['_embedded']['records']:
            asset_code = asset.get('asset_code', 'XLM')
            asset_issuer = asset.get('asset_issuer', 'XLM')
            result[f"{asset_code}-{asset_issuer[:4]}..{asset_issuer[-4:]}"] = f"{asset_code}-{asset_issuer}"
    except:
        pass

    return jsonify(result)


@blueprint.route('/lab/data/<account_id>')
async def cmd_data(account_id):
    result = {}
    try:
        account = Server(horizon_url="https://horizon.stellar.org").accounts().account_id(account_id).call()
        for data_name in account.get('data'):
            result[f"{data_name}={decode_data_value(account['data'][data_name])}"] = data_name
    except:
        pass
    result['mtl_delegate if you want delegate your mtl votes'] = 'mtl_delegate'
    result['mtl_donate if you want donate'] = 'mtl_donate'
    return jsonify(result)


@blueprint.route('/lab/offers/<account_id>')
async def cmd_offers(account_id):
    result = {}
    try:
        account = Server(horizon_url="https://horizon.stellar.org").offers().for_account(account_id).call()
        for record in account['_embedded']['records']:
            result[f"{record['id']} selling {record['amount']} {record['selling']['asset_code']} " +
                   f"for {record['buying']['asset_code']} price {record['price']}"] = record['id']
    except:
        pass
    return jsonify(result)


@blueprint.route('/lab/path/<asset_from>/<asset_for>/<asset_sum>')
async def cmd_path(asset_from, asset_for, asset_sum):
    result = {}
    try:
        account = Server(horizon_url="https://horizon.stellar.org").strict_send_paths(
            source_asset=decode_asset(asset_from),
            source_amount=float2str(asset_sum),
            destination=[decode_asset(asset_for)]).call()
        for record in account['_embedded']['records']:
            result[f"{record['destination_amount']} {record['destination_asset_code']}"] = json.dumps(record['path'])
    except:
        pass
    return jsonify(result)


if __name__ == '__main__':
    asyncio.run(cmd_path('XLM', 'BTCMTL-GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V', '150'))
