import requests
from flask import Blueprint, render_template, jsonify, request
from stellar_sdk import Server, TransactionBuilder, Network, Asset

from utils import decode_data_value

laboratory_blueprint = Blueprint('laboratory', __name__)


@laboratory_blueprint.route('/laboratory')
def cmd_laboratory():
    return render_template('laboratory.html')


@laboratory_blueprint.route('/mtl_accounts')
def cmd_mtl_accounts():
    result = {
        "Администрация": "GBSCMGJCE4DLQ6TYRNUMXUZZUXGZBM4BXVZUIHBBL5CSRRW2GWEHUADM",
        "Эмиссии": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "БДМ основной": "GDEK5KGFA3WCG3F2MLSXFGLR4T4M6W6BMGWY6FBDSDQM6HXFMRSTEWBW",
        "Бот дивидендов": "GDNHQWZRZDZZBARNOH6VFFXMN6LBUNZTZHOKBUT7GREOWBTZI4FGS7IQ",
        "Директорский": "GC72CB75VWW7CLGXS76FGN3CC5K7EELDAQCPXYMZLNMOTC42U3XJBOSS",
        "МАБИЗ": "GDWLM7WZP7PEVO3OBNEUJY7HX3DLJ3LQNNVTJLQIO6SYK2SHA6VMABIZ",
        "Хранилище_битков": "GATUN5FV3QF35ZMU3C63UZ63GOFRYUHXV2SHKNTKPBZGYF2DU3B7IW6Z",
        "эмиссия ЮСДМ": "GAZ37MDGUSED4AEHZ45RYZWLWTFUVMQ2LEG22Q44X6E2QQN5GLZXUSDM",
        "Binance Deposits": "GABFQIK63R2NETJM7T673EAMZN4RJLLGP3OFUEJU5SZVTGWUKULZJNL6",
        "LBTC fond": "GAUBJ4CTRF42Z7OM7QXTAQZG6BEMNR3JZY57Z4LB3PXSDJXE5A5GIGJB",
        "MTL city": "GDUI7JVKWZV4KJVY4EJYBXMGXC2J3ZC67Z6O5QFP4ZMVQM2U5JXK2OK3",
        "MTL DeFi": "GBTOF6RLHRPG5NRIU6MQ7JGMCV7YHL5V33YYC76YYG4JUKCJTUP5DEFI",
        "MyMtlWalletBot": "GBSNN2SPYZB2A5RPDTO3BLX4TP5KNYI7UMUABUS3TYWWEWAAM2D7CMMW"
    }
    return jsonify(result)


@laboratory_blueprint.route('/sequence/<account_id>')
def cmd_sequence(account_id):
    try:
        r = requests.get('https://horizon.stellar.org/accounts/' + account_id).json()
        sequence = int(r['sequence']) + 1
    except:
        sequence = 0
    return jsonify({'sequence': str(sequence)})


@laboratory_blueprint.route('/mtl_assets')
def cmd_mtl_assets():
    result = {
        "XLM": "XLM",
        "MTL": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "NIRO": "GCOP3XDXTEHWPRXT3NSPPPR3RCHLLK6CUZI3S6RUWGEAKDD73IEU5H3E",
        "EHIN": "GDI4PH6R2B4JDTMONRJA3BV4L3IBMXHWFCQPP5VTDSD3EE2ZFZGQJZZO",
        "GPA": "GBGGX7QD3JCPFKOJTLBRAFU3SIME3WSNDXETWI63EDCORLBB6HIP2CRR",
        "GPACAR": "GBGGX7QD3JCPFKOJTLBRAFU3SIME3WSNDXETWI63EDCORLBB6HIP2CRR",
        "MrxpInvest": "GDAJVYFMWNIKYM42M6NG3BLNYXC3GE3WMEZJWTSYH64JLZGWVJPTGGB7",
        "MrxpCorrect": "GDAJVYFMWNIKYM42M6NG3BLNYXC3GE3WMEZJWTSYH64JLZGWVJPTGGB7",
        "AUMTL": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "AUDEBT": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "BTCMTL": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "BTCDEBT": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "EURMTL": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "EURDEBT": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "MTLand": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "MTLMiner": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "MTLRECT": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "BIOM": "GAOIY67QNDNFSOKTLSBGI4ZDLIEEPNKYBS7ZNJSSM7FRE6XX2MKSEZYW",
        "MTLCITY": "GDUI7JVKWZV4KJVY4EJYBXMGXC2J3ZC67Z6O5QFP4ZMVQM2U5JXK2OK3",
        "MTLDVL": "GAMU3C7Q7CUUC77BAN5JLZWE7VUEI4VZF3KMCMM3YCXLZPBYK5Q2IXTA",
        "SATSMTL": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
        "MAT": "GBJ3HT6EDPWOUS3CUSIJW5A4M7ASIKNW4WFTLG76AAT5IE6VGVN47TIC",
        "USDM": "GDHDC4GBNPMENZAOBB4NCQ25TGZPDRK6ZGWUGSI22TVFATOLRPSUUSDM",
        "MTLFEST": "GCGWAPG6PKBMHEEAHRLTWHFCAGZTQZDOXDMWBUBCXHLQBSBNWFRYFEST",
        "MTLand": "GC7XRK2D6XDNN2LCOJEAPXNAQA3ZBUR3ZR6S4VI4T46GSRM3F6BMLAND",
        "MMiner": "GBL5CHD6UNJ5COC2D27RVIH5U67T6X3ZCMWTNE3K5MC6XTD7K56MINER",
        "Agora": "GBGGX7QD3JCPFKOJTLBRAFU3SIME3WSNDXETWI63EDCORLBB6HIP2CRR",
    }
    return jsonify(result)


def decode_asset(asset):
    arr = asset.split('-')
    if arr[0] == 'XLM':
        return Asset(arr[0])
    else:
        return Asset(arr[0], arr[1])


@laboratory_blueprint.route('/build_xdr', methods=['POST'])
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


@laboratory_blueprint.route('/assets/<account_id>')
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


@laboratory_blueprint.route('/data/<account_id>')
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
