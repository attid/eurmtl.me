import json
from datetime import datetime

import requests
from stellar_sdk import (
    FeeBumpTransactionEnvelope,
    HashMemo,
    Network,
    NoneMemo,
    TextMemo,
    TransactionEnvelope,
    PathPaymentStrictSend,
    ManageSellOffer

)
from stellar_sdk.exceptions import NotFoundError


def get_key_sort(key, idx=1):
    return key[idx]


def check_publish_state(tx_hash: str) -> int:
    rq = requests.get(f'https://horizon.stellar.org/transactions/{tx_hash}')
    if rq.status_code == 200:
        if rq.json()['successful']:
            return 1
        else:
            return 10
    else:
        return 0

    # !pip install urllib3 --upgrade
    # !pip install requests --upgrade


def decode_xdr_from_base64(xdr):
    import base64
    xdr = xdr.replace("%3D", "=")
    decoded_bytes = base64.urlsafe_b64decode(xdr)
    decoded_str = decoded_bytes.decode('utf-8')
    # print(decoded_str)
    decoded_json = json.loads(decoded_str)
    print(decoded_json)


def decode_xdr_to_base64(xdr):
    transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE).transaction
    new_json = {'attributes': {}, 'feeBumpAttributes': {'maxFee': '10101'}, 'operations': []}
    # 'memoType': 'MEMO_TEXT', 'memoContent': 'mymemohere'
    # print(transaction.source)
    fee = str(int(transaction.fee / len(transaction.operations)))
    new_json['attributes'] = {'sourceAccount': transaction.source.account_id, 'sequence': str(transaction.sequence),
                              'fee': fee, 'baseFee': '100', 'minFee': '5000'}

    for op_idx, operation in enumerate(transaction.operations):
        # Задаём имя операции
        op_name = type(operation).__name__
        op_name = op_name[0].lower() + op_name[1:]
        op_json = {'id': op_idx, 'attributes': {}, 'name': op_name}

        # Декодируем атрибуты операции в зависимости от её типа
        from stellar_sdk import Payment, ChangeTrust, CreateAccount, SetOptions, ManageData
        if isinstance(operation, Payment):
            op_json['attributes'] = {'destination': operation.destination.account_id,
                                     'asset': operation.asset.to_dict(),
                                     'amount': float2str(operation.amount),
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, ChangeTrust):
            op_json['attributes'] = {'asset': operation.asset.to_dict(),
                                     'limit': operation.limit,
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, ManageData):
            op_json['attributes'] = {'name': operation.data_name,
                                     'value': operation.data_value.decode(),
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, CreateAccount):
            op_json['attributes'] = {'destination': operation.destination,
                                     'startingBalance': operation.starting_balance,
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, ManageSellOffer):
            op_json['attributes'] = {'amount': operation.amount,
                                     'price': operation.price.n/operation.price.d,
                                     'offerId': operation.offer_id,
                                     'selling': operation.selling.to_dict(),
                                     'buying': operation.buying.to_dict(),
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }

        # Добавить здесь декодирование других типов операций по аналогии
        elif isinstance(operation, SetOptions):
            op_json['attributes'] = {
                'signer': None if operation.signer is None else {'type': 'ed25519PublicKey',
                                                                 'content': operation.signer.signer_key.encoded_signer_key,
                                                                 'weight': str(operation.signer.weight)},
                'sourceAccount': operation.source.account_id if operation.source is not None else None,
                'masterWeight': operation.master_weight,
                'lowThreshold': operation.low_threshold,
                'medThreshold': operation.med_threshold,
                'highThreshold': operation.high_threshold,
                'homeDomain': operation.home_domain
            }
        # {'attributes': {'sourceAccount': 'GAQ5ERJVI6IW5UVNPEVXUUVMXH3GCDHJ4BJAXMAAKPR5VBWWAUOMABIZ', 'sequence': '198986603622825985', 'fee': '5000', 'baseFee': '100', 'minFee': '100'},
        # 'feeBumpAttributes': {'maxFee': '100'}, 'operations': [
        # {'id': 1688742251202, 'name': 'pathPaymentStrictSend',
        # 'attributes': {'destination': 'GAQ5ERJVI6IW5UVNPEVXUUVMXH3GCDHJ4BJAXMAAKPR5VBWWAUOMABIZ',
        # 'sendAsset': {'type': 'credit_alphanum12', 'code': 'MTLBR', 'issuer': 'GAMU3C7Q7CUUC77BAN5JLZWE7VUEI4VZF3KMCMM3YCXLZPBYK5Q2IXTA'},
        # 'path': [],
        # 'destAsset': {'type': 'credit_alphanum4', 'code': 'TIC', 'issuer': 'GBJ3HT6EDPWOUS3CUSIJW5A4M7ASIKNW4WFTLG76AAT5IE6VGVN47TIC'},
        # 'destMin': '22.0835395',
        # 'sendAmount': '22083.5395092'}}]}
        elif isinstance(operation, PathPaymentStrictSend):
            op_json['attributes'] = {'sendAsset': operation.send_asset.to_dict(),
                                     'destination': operation.destination.account_id,
                                     'path': operation.path,
                                     'destMin': operation.dest_min,
                                     'sendAmount': operation.send_amount,
                                     'destAsset': operation.dest_asset.to_dict(),
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }

        else:
            op_json['attributes'] = {
                'detail': 'Unsupported operation type'
            }
            print('00000000___00000000', type(operation).__name__)

        new_json['operations'].append(op_json)
    print(new_json)
    # Convert the dictionary into JSON
    json_data = json.dumps(new_json)
    # Convert the JSON data into bytes
    json_bytes = json_data.encode('utf-8')
    # Encode the bytes into base64
    import base64
    encoded_bytes = base64.urlsafe_b64encode(json_bytes)
    # Convert the base64 bytes into a string
    encoded_str = encoded_bytes.decode('utf-8')

    return encoded_str


def float2str(f) -> str:
    if isinstance(f, str):
        f = f.replace(',', '.')
        f = float(f)
    s = "%.7f" % f
    while len(s) > 1 and s[-1] in ('0', '.'):
        l = s[-1]
        s = s[0:-1]
        if l == '.':
            break
    return s


def check_response(data):
    import hashlib
    import hmac
    d = data.copy()
    del d['hash']
    d_list = []
    for key in sorted(d.keys()):
        if not d[key] is None:
            d_list.append(key + '=' + d[key])
    data_string = bytes('\n'.join(d_list), 'utf-8')

    # secret_key = hashlib.sha256(app.config['TELEGRAM_BOT_TOKEN'].encode('utf-8')).digest()
    # hmac_string = hmac.new(secret_key, data_string, hashlib.sha256).hexdigest()
    # i#f hmac_string == data['hash']:
    #    return True
    return False


def address_id_to_link(key) -> str:
    start_url = "https://stellar.expert/explorer/public/account"
    return f'<a href="{start_url}/{key}" target="_blank">{key[:4] + ".." + key[-4:]}</a>'


def asset_to_link(operation_asset) -> str:
    start_url = "https://stellar.expert/explorer/public/asset"
    if operation_asset.code == 'XLM':
        return f'<a href="{start_url}/{operation_asset.code}" target="_blank">{operation_asset.code}</a>'
    else:
        return f'<a href="{start_url}/{operation_asset.code}-{operation_asset.issuer}" target="_blank">{operation_asset.code}</a>'


def decode_xdr_to_text(xdr):
    result = []
    data_exist = False

    if FeeBumpTransactionEnvelope.is_fee_bump_transaction_envelope(xdr):
        fee_transaction = FeeBumpTransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        transaction = fee_transaction.transaction.inner_transaction_envelope
    else:
        transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    result.append(f"Sequence Number {transaction.transaction.sequence}")

    if transaction.transaction.preconditions.time_bounds.max_time > 0:
        human_readable_time = datetime.utcfromtimestamp(
            transaction.transaction.preconditions.time_bounds.max_time).strftime('%d.%m.%Y %H:%M:%S')
        result.append(f"MaxTime ! {human_readable_time} UTC")

    server_sequence = int(
        requests.get('https://horizon.stellar.org/accounts/' + transaction.transaction.source.account_id).json()[
            'sequence'])
    if server_sequence + 1 != transaction.transaction.sequence:
        result.append(f"<div style=\"color: red;\">Bad Sequence ! </div>")
    result.append(f"Операции с аккаунта {address_id_to_link(transaction.transaction.source.account_id)}")
    #    if transaction.transaction.memo.__class__ == TextMemo:
    #        memo: TextMemo = transaction.transaction.memo
    #        result.append(f'  Memo "{memo.memo_text.decode()}"\n')
    memo = transaction.transaction.memo
    if isinstance(memo, NoneMemo):
        result.append('  No memo\n')
    elif isinstance(memo, TextMemo):
        result.append(f'  Memo text: "{memo.memo_text.decode()}"\n')
    elif isinstance(memo, HashMemo):
        result.append(f'  Memo hash (hex): "{memo.memo_hash.hex()}"\n')
    else:
        result.append(
            f'  Memo is of unsupported type {type(memo).__name__}...\n'
        )

    result.append(f"  Всего {len(transaction.transaction.operations)} операций\n")

    for idx, operation in enumerate(transaction.transaction.operations):
        result.append(f"Операция {idx} - {type(operation).__name__}")
        # print('bad xdr', idx, operation)
        if operation.source:
            result.append(f"*** для аккаунта {address_id_to_link(operation.source.account_id)}")
        if type(operation).__name__ == "Payment":
            data_exist = True
            result.append(
                f"    Перевод {operation.amount} {asset_to_link(operation.asset)} на аккаунт {address_id_to_link(operation.destination.account_id)}")
            if operation.asset.code != 'XLM':
                # check trust line
                if operation.destination.account_id != operation.asset.issuer:
                    destination_account = requests.get(
                        'https://horizon.stellar.org/accounts/' + operation.destination.account_id).json()
                    asset_found = any(
                        balance.get('asset_code') == operation.asset.code for balance in
                        destination_account['balances'])
                    if not asset_found:
                        result.append(f"<div style=\"color: red;\">Asset not found ! </div>")
                source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
                # check balance
                if source_id != operation.asset.issuer:
                    source_account = requests.get('https://horizon.stellar.org/accounts/' + source_id).json()
                    source_sum = sum(float(balance.get('balance')) for balance in source_account['balances'] if
                                     balance.get('asset_code') == operation.asset.code)
                    if source_sum < float(operation.amount):
                        result.append(f"<div style=\"color: red;\">Not enough balance ! </div>")

                # check sale
                source_sale = requests.get('https://horizon.stellar.org/accounts/' + source_id + '/offers').json()
                sale_found = any(
                    record['selling'].get('asset_code') == operation.asset.code for record in
                    source_sale['_embedded']['records'])
                if sale_found:
                    result.append(f"<div style=\"color: red;\">Sale found! Do you have enough amount? </div>")

            continue
        if type(operation).__name__ == "SetOptions":
            data_exist = True
            if operation.signer:
                result.append(
                    f"    Изменяем подписанта {address_id_to_link(operation.signer.signer_key.encoded_signer_key)} новые голоса : {operation.signer.weight}")
            if operation.med_threshold:
                data_exist = True
                result.append(f"Установка нового требования. Нужно будет {operation.med_threshold} голосов")
            continue
        if type(operation).__name__ == "ChangeTrust":
            data_exist = True
            if operation.limit == '0':
                result.append(
                    f"    Закрываем линию доверия к токену {asset_to_link(operation.asset)} от аккаунта {address_id_to_link(operation.asset.issuer)}")
            else:
                result.append(
                    f"    Открываем линию доверия к токену {asset_to_link(operation.asset)} от аккаунта {address_id_to_link(operation.asset.issuer)}")

            continue
        if type(operation).__name__ == "CreateClaimableBalance":
            data_exist = True
            result.append(f"  Спам {operation.asset.code}")
            result.append(f"  Остальные операции игнорируются.")
            break
        if type(operation).__name__ == "ManageSellOffer":
            data_exist = True
            result.append(
                f"    Офер на продажу {operation.amount} {asset_to_link(operation.selling)} по цене {operation.price.n / operation.price.d} {asset_to_link(operation.buying)}")
            continue
        if type(operation).__name__ == "CreatePassiveSellOffer":
            data_exist = True
            result.append(
                f"    Пассивный офер на продажу {operation.amount} {asset_to_link(operation.selling)} по цене {operation.price.n / operation.price.d} {asset_to_link(operation.buying)}")
            continue
        if type(operation).__name__ == "ManageBuyOffer":
            data_exist = True
            result.append(
                f"    Офер на покупку {operation.amount} {asset_to_link(operation.buying)} по цене {operation.price.n / operation.price.d} {asset_to_link(operation.selling)}")
            continue
        if type(operation).__name__ == "PathPaymentStrictSend":
            data_exist = True
            result.append(
                f"    Покупка {address_id_to_link(operation.destination.account_id)}, шлем {asset_to_link(operation.send_asset)} {operation.send_amount} в обмен на {asset_to_link(operation.dest_asset)} min {operation.dest_min} ")
            continue
        if type(operation).__name__ == "PathPaymentStrictReceive":
            data_exist = True
            result.append(
                f"    Продажа {address_id_to_link(operation.destination.account_id)}, Получаем {asset_to_link(operation.send_asset)} max {operation.send_max} в обмен на {asset_to_link(operation.dest_asset)} {operation.dest_amount} ")
            continue
        if type(operation).__name__ == "ManageData":
            data_exist = True
            result.append(
                f"    ManageData {operation.data_name} = {operation.data_value} ")
            continue
        if type(operation).__name__ == "CreateAccount":
            data_exist = True
            result.append(
                f"    Создание аккаунта {address_id_to_link(operation.destination)} с суммой {operation.starting_balance} XLM")
            continue
        if type(operation).__name__ == "AccountMerge":
            data_exist = True
            result.append(
                f"    Слияние аккаунта c {address_id_to_link(operation.destination.account_id)} ")
            continue
        if type(operation).__name__ == "ClaimClaimableBalance":
            data_exist = True
            result.append(f"    ClaimClaimableBalance {address_id_to_link(operation.balance_id)}")
            continue
        if type(operation).__name__ == "BeginSponsoringFutureReserves":
            data_exist = True
            result.append(f"    BeginSponsoringFutureReserves {address_id_to_link(operation.sponsored_id)}")
            continue
        if type(operation).__name__ == "EndSponsoringFutureReserves":
            data_exist = True
            result.append(f"    EndSponsoringFutureReserves")
            continue
        if type(operation).__name__ in ["PathPaymentStrictSend", "ManageBuyOffer", "ManageSellOffer", "AccountMerge",
                                        "PathPaymentStrictReceive", "ClaimClaimableBalance", "CreateAccount",
                                        "CreateClaimableBalance", "ChangeTrust", "SetOptions", "Payment", "ManageData",
                                        "BeginSponsoringFutureReserves", "EndSponsoringFutureReserves",
                                        "CreatePassiveSellOffer"]:
            continue

        data_exist = True
        result.append(f"Прости хозяин, не понимаю")
        print('bad xdr', idx, operation)
    if data_exist:
        return result
    else:
        return []


if __name__ == '__main__':
    # print(decode_xdr_to_text(
    #    'AAAAAgAAAAAh0kU1R5Fu0q15K3pSrLn2YQzp4FILsABT49qG1gUcwAAPabUCwvFDAAAAAQAAAAEAAAAAAAAAAAAAAABkpu69AAAAAAAAAAEAAAAAAAAADQAAAAJNVExCUgAAAAAAAAAAAAAAGU2L8PipQX/hA3qV5sT9aERyuS7UwTGbwK68vDhXYaQAAAAzatC2FAAAAAAh0kU1R5Fu0q15K3pSrLn2YQzp4FILsABT49qG1gUcwAAAAAFUSUMAAAAAAFOzz8Qb7OpLYqSQm3QcZ8EkKbblizWb/gAn1BPVNVvPAAAAAA0prkMAAAAAAAAAAAAAAAA='))
    # exit()
    # simple way to find error in editing
    l = 'https://laboratory.stellar.org/#txbuilder?params=eyJhdHRyaWJ1dGVzIjp7InNvdXJjZUFjY291bnQiOiJHRE9KSzdVQVVNUVg1SVpFUllQTkJQUVlRM1NIUEtHTEY1TUJVS1dMREwyVVYyQVk2QklTM1RGTSIsInNlcXVlbmNlIjoiMjAwNTQ2NzU0Nzg4MDY1Mjg4IiwiZmVlIjoiMTAwMCIsImJhc2VGZWUiOiIxMDAiLCJtaW5GZWUiOiI1MDAwIn0sImZlZUJ1bXBBdHRyaWJ1dGVzIjp7Im1heEZlZSI6IjEwMTAxIn0sIm9wZXJhdGlvbnMiOlt7ImlkIjoxNjg5MDcwNzE0MjQ3LCJuYW1lIjoibWFuYWdlU2VsbE9mZmVyIiwiYXR0cmlidXRlcyI6eyJzZWxsaW5nIjp7InR5cGUiOiJuYXRpdmUiLCJjb2RlIjoiIiwiaXNzdWVyIjoiIn0sImJ1eWluZyI6eyJ0eXBlIjoiY3JlZGl0X2FscGhhbnVtMTIiLCJjb2RlIjoiZXJ0ZXJ0ZXJ0ZXJ0IiwiaXNzdWVyIjoiR0RPSks3VUFVTVFYNUlaRVJZUE5CUFFZUTNTSFBLR0xGNU1CVUtXTERMMlVWMkFZNkJJUzNURk0ifSwiYW1vdW50IjoiMjMuMyIsInByaWNlIjoiMjUuNTYiLCJvZmZlcklkIjoiMCJ9fV19&network=public'
    l = l.split('/')[-1].split('=')[1].split('&')[0]
    decode_xdr_from_base64(l)
    e = decode_xdr_to_base64(
        'AAAAAgAAAADclX6AoyF+oySOHtC+GIbkd6jLL1gaKssa9UroGPBRLQAAA+gCyHw2AAAACAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAwAAAAAAAAACZXJ0ZXJ0ZXJ0ZXJ0AAAAANyVfoCjIX6jJI4e0L4YhuR3qMsvWBoqyxr1SugY8FEtAAAAAA3jTEAAAAJ/AAAAGQAAAAAAAAAAAAAAAAAAAAA=')
    decode_xdr_from_base64(e)
    print(f'https://laboratory.stellar.org/#txbuilder?params={e}&network=public')
    pass
