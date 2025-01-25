import asyncio
import base64
import json
from datetime import datetime

import aiohttp
import requests
from quart import session, flash
from stellar_sdk import (
    FeeBumpTransactionEnvelope,
    HashMemo,
    Network,
    NoneMemo,
    TextMemo,
    TransactionEnvelope,
    PathPaymentStrictSend,
    ManageSellOffer, Transaction, Keypair, Server, Asset, TransactionBuilder, ServerAsync, AiohttpClient,
    CreatePassiveSellOffer, ManageBuyOffer, Clawback, SetTrustLineFlags, TrustLineFlags
)
from stellar_sdk.sep import stellar_uri

from db import mongo
from db.mongo import get_asset_by_code
from db.sql_models import Signers, Transactions, Signatures
from db.sql_pool import db_pool
from other.config_reader import config

main_fund_address = 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'


def get_key_sort(key, idx=1):
    return key[idx]


def check_publish_state(tx_hash: str) -> (int, str):
    rq = requests.get(f'https://horizon.stellar.org/transactions/{tx_hash}')
    if rq.status_code == 200:
        date = rq.json()['created_at'].replace('T', ' ').replace('Z', '')
        with db_pool() as db_session:
            transaction = db_session.query(Transactions).filter(Transactions.hash == tx_hash).first()
            if transaction and transaction.state != 2:
                transaction.state = 2
                db_session.commit()
        if rq.json()['successful']:
            return 1, date
        else:
            return 10, date
    else:
        return 0, 'Unknown'

    # !pip install urllib3 --upgrade
    # !pip install requests --upgrade


def decode_xdr_from_base64(xdr):
    import base64
    xdr = xdr.replace("%3D", "=")
    decoded_bytes = base64.urlsafe_b64decode(xdr)
    decoded_str = decoded_bytes.decode('utf-8')
    # print(decoded_str)
    decoded_json = json.loads(decoded_str)
    # print(decoded_json)


def decode_xdr_to_base64(xdr, return_json=False):
    transaction_envelope = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    transaction: Transaction = transaction_envelope.transaction
    new_json = {'attributes': {}, 'feeBumpAttributes': {'maxFee': '10101'}, 'operations': []}

    fee = str(int(transaction.fee / len(transaction.operations)))
    new_json['attributes'] = {'sourceAccount': transaction.source.account_id, 'sequence': str(transaction.sequence),
                              'fee': fee, 'baseFee': '100', 'minFee': '5000'}

    if transaction.memo:
        if isinstance(transaction.memo, TextMemo):
            new_json['attributes']['memoType'] = 'MEMO_TEXT'
            new_json['attributes']['memoContent'] = transaction.memo.memo_text.decode()
        elif isinstance(transaction.memo, HashMemo):
            new_json['attributes']['memoType'] = 'MEMO_HASH'
            new_json['attributes']['memoContent'] = transaction.memo.memo_hash.hex()

    for op_idx, operation in enumerate(transaction.operations):
        # Задаём имя операции
        op_name = type(operation).__name__
        op_name = op_name[0].lower() + op_name[1:]
        op_json = {'id': op_idx, 'attributes': {}, 'name': op_name}

        # Декодируем атрибуты операции в зависимости от её типа
        from stellar_sdk import Payment, ChangeTrust, CreateAccount, SetOptions, ManageData
        if isinstance(operation, Payment):
            # noinspection PyTypedDict
            op_json['attributes'] = {'destination': operation.destination.account_id,
                                     'asset': operation.asset.to_dict(),
                                     'amount': float2str(operation.amount),
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, ChangeTrust):
            # noinspection PyTypedDict
            op_json['attributes'] = {'asset': operation.asset.to_dict(),
                                     'limit': operation.limit,
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, ManageData):
            # noinspection PyTypedDict
            op_json['attributes'] = {'name': operation.data_name,
                                     'dataName': operation.data_name,
                                     'value': operation.data_value.decode() if operation.data_value is not None else "",
                                     'dataValue': operation.data_value.decode() if operation.data_value is not None else "",
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, CreateAccount):
            # noinspection PyTypedDict
            op_json['attributes'] = {'destination': operation.destination,
                                     'startingBalance': operation.starting_balance,
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, SetTrustLineFlags):
            # noinspection PyTypedDict
            op_json['attributes'] = {'trustor': operation.trustor,
                                     'asset': operation.asset.to_dict(),
                                     'setFlags': operation.set_flags.value if operation.set_flags else None,
                                     'clearFlags': operation.clear_flags.value if operation.clear_flags else None,
                                     'sourceAccount': operation.source.account_id if operation.source else None
                                     }
        elif isinstance(operation, ManageSellOffer) or isinstance(operation, ManageBuyOffer):
            # noinspection PyTypedDict
            op_json['attributes'] = {'amount': operation.amount,
                                     'price': operation.price.n / operation.price.d,
                                     'offerId': operation.offer_id,
                                     'selling': operation.selling.to_dict(),
                                     'buying': operation.buying.to_dict(),
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, CreatePassiveSellOffer):
            # noinspection PyTypedDict
            op_json['attributes'] = {'amount': operation.amount,
                                     'price': operation.price.n / operation.price.d,
                                     'selling': operation.selling.to_dict(),
                                     'buying': operation.buying.to_dict(),
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, Clawback):
            # noinspection PyTypedDict
            op_json['attributes'] = {'amount': operation.amount,
                                     'asset': operation.asset.to_dict(),
                                     'from': operation.from_.account_id,
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, SetOptions):
            if operation.signer:
                op_json['name'] = 'setOptionsSigner'
                # noinspection PyTypedDict
                op_json['attributes'] = {'signerAccount': operation.signer.signer_key.encoded_signer_key,
                                         'weight': str(operation.signer.weight)}
            else:
                if operation.low_threshold and operation.med_threshold and operation.high_threshold:
                    if operation.low_threshold == operation.med_threshold == operation.high_threshold:
                        threshold = operation.low_threshold
                    else:
                        threshold = f"{operation.low_threshold}/{operation.med_threshold}/{operation.high_threshold}"
                else:
                    threshold = None
                # noinspection PyTypedDict
                op_json['attributes'] = {
                    'sourceAccount': operation.source.account_id if operation.source is not None else None,
                    'master': operation.master_weight,
                    'threshold': threshold,
                    'home': operation.home_domain
                }
        elif isinstance(operation, PathPaymentStrictSend):
            # noinspection PyTypedDict
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
    # print(new_json)
    if return_json:
        return new_json
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


def address_id_to_link(key) -> str:
    start_url = "https://stellar.expert/explorer/public/account"
    return f'<a href="{start_url}/{key}" target="_blank">{key[:4] + ".." + key[-4:]}</a>'


def pool_id_to_link(key) -> str:
    start_url = "https://stellar.expert/explorer/public/liquidity-pool"
    return f'<a href="{start_url}/{key}" target="_blank">{key[:4] + ".." + key[-4:]}</a>'


async def asset_to_link(operation_asset) -> str:
    start_url = "https://stellar.expert/explorer/public/asset"
    if operation_asset.code == 'XLM':
        return f'<a href="{start_url}/{operation_asset.code}" target="_blank">{operation_asset.code}⭐</a>'
    else:
        # add * if we have asset in DB
        asset = await get_asset_by_code(operation_asset.code, False)
        if asset and asset.issuer == operation_asset.issuer:
            return f'<a href="{start_url}/{operation_asset.code}-{operation_asset.issuer}" target="_blank">{operation_asset.code}⭐</a>'
        return f'<a href="{start_url}/{operation_asset.code}-{operation_asset.issuer}" target="_blank">{operation_asset.code}</a>'


def check_asset(asset, cash: dict):
    try:
        if f"{asset.code}-{asset.issuer}" in cash.keys():
            r = cash[f"{asset.code}-{asset.issuer}"]
        else:
            r = requests.get(
                f'https://horizon.stellar.org/assets?asset_code={asset.code}&asset_issuer={asset.issuer}').json()
            cash[f"{asset.code}-{asset.issuer}"] = r
        if r["_embedded"]["records"]:
            return ''
    except:
        pass
    return f"<div style=\"color: red;\">Asset {asset.code} not exist ! </div>"


def get_account(account_id, cash):
    if account_id in cash.keys():
        r = cash[account_id]
    else:
        r = requests.get('https://horizon.stellar.org/accounts/' + account_id).json()
        if r.get('id'):
            cash[account_id] = r
        else:
            cash[account_id] = {'balances': []}
            r = cash[account_id]
    return r


def get_offers(account_id, cash):
    if f'{account_id}-offers' in cash.keys():
        r = cash[f'{account_id}-offers']
    else:
        r = requests.get(f'https://horizon.stellar.org/accounts/{account_id}/offers').json()
        cash[f'{account_id}-offers'] = r
    return r


async def decode_xdr_to_text(xdr, only_op_number=None):
    result = []
    cash = {}
    data_exist = False

    if FeeBumpTransactionEnvelope.is_fee_bump_transaction_envelope(xdr):
        fee_transaction = FeeBumpTransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        transaction = fee_transaction.transaction.inner_transaction_envelope
    else:
        transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    result.append(f"Sequence Number {transaction.transaction.sequence}")
    if transaction.transaction.fee < 5000:
        result.append(f"<div style=\"color: orange;\">Bad Fee {transaction.transaction.fee}! </div>")
    else:
        result.append(f"Fee {transaction.transaction.fee}")

    if (transaction.transaction.preconditions and transaction.transaction.preconditions.time_bounds and
            transaction.transaction.preconditions.time_bounds.max_time > 0):
        human_readable_time = datetime.utcfromtimestamp(
            transaction.transaction.preconditions.time_bounds.max_time).strftime('%d.%m.%Y %H:%M:%S')
        result.append(f"MaxTime ! {human_readable_time} UTC")

    server_sequence = int(get_account(transaction.transaction.source.account_id, cash)['sequence'])
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
        if only_op_number:
            if idx == 0:
                result.clear()  # clear transaction info
            if idx != only_op_number:
                continue
            if idx > only_op_number:
                break

        result.append(f"Операция {idx} - {type(operation).__name__}")
        # print('bad xdr', idx, operation)
        if operation.source:
            result.append(f"*** для аккаунта {address_id_to_link(operation.source.account_id)}")
        if type(operation).__name__ == "Payment":
            data_exist = True
            result.append(
                f"    Перевод {operation.amount} {await asset_to_link(operation.asset)} на аккаунт {address_id_to_link(operation.destination.account_id)}")
            if operation.asset.code != 'XLM':
                # check valid asset
                result.append(check_asset(operation.asset, cash))
                # check trust line
                if operation.destination.account_id != operation.asset.issuer:
                    destination_account = get_account(operation.destination.account_id, cash)
                    asset_found = any(
                        balance.get('asset_code') == operation.asset.code for balance in
                        destination_account['balances'])
                    if not asset_found:
                        result.append(f"<div style=\"color: red;\">Asset not found ! </div>")
                source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
                # check balance
                if source_id != operation.asset.issuer:
                    source_account = get_account(source_id, cash)
                    source_sum = sum(float(balance.get('balance')) for balance in source_account['balances'] if
                                     balance.get('asset_code') == operation.asset.code)
                    if source_sum < float(operation.amount):
                        result.append(f"<div style=\"color: red;\">Not enough balance ! </div>")

                # check sale
                source_sale = get_offers(source_id, cash)
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
            if operation.med_threshold or operation.low_threshold or operation.high_threshold:
                data_exist = True
                result.append(f"Установка нового требования. Нужно будет {operation.low_threshold}/{operation.med_threshold}/{operation.high_threshold} голосов")
            if operation.home_domain:
                data_exist = True
                result.append(f"Установка нового домена {operation.home_domain}")
            if operation.master_weight is not None:
                data_exist = True
                result.append(f"Установка master_weight {operation.master_weight}")

            continue
        if type(operation).__name__ == "ChangeTrust":
            data_exist = True
            source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
            if operation.asset.type == 'liquidity_pool_shares':
                if operation.limit == '0':
                    result.append(
                        f"    Закрываем линию доверия к пулу {pool_id_to_link(operation.asset.liquidity_pool_id)} {await asset_to_link(operation.asset.asset_a)}/{await asset_to_link(operation.asset.asset_b)}")
                else:
                    result.append(
                        f"    Открываем линию доверия к пулу {pool_id_to_link(operation.asset.liquidity_pool_id)} {await asset_to_link(operation.asset.asset_a)}/{await asset_to_link(operation.asset.asset_b)}")
            else:
                # check valid asset
                result.append(check_asset(operation.asset, cash))
                if operation.asset.issuer == source_id:
                    result.append(f"<div style=\"color: red;\">MELFORMET You can`t open trustline for yourself! </div>")

                if operation.limit == '0':
                    result.append(
                        f"    Закрываем линию доверия к токену {await asset_to_link(operation.asset)} от аккаунта {address_id_to_link(operation.asset.issuer)}")
                else:
                    result.append(
                        f"    Открываем линию доверия к токену {await asset_to_link(operation.asset)} от аккаунта {address_id_to_link(operation.asset.issuer)}")

            continue
        if type(operation).__name__ == "CreateClaimableBalance":
            data_exist = True
            result.append(f"  Спам {operation.asset.code}")
            result.append(f"  Остальные операции игнорируются.")
            break
        if type(operation).__name__ == "ManageSellOffer":
            data_exist = True
            # check valid asset
            result.append(check_asset(operation.selling, cash))
            result.append(check_asset(operation.buying, cash))

            result.append(
                f"    Офер на продажу {operation.amount} {await asset_to_link(operation.selling)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.buying)}")
            if operation.offer_id != 0:
                result.append(
                    f"    Номер офера <a href=\"https://stellar.expert/explorer/public/offer/{operation.offer_id}\">{operation.offer_id}</a>")
            # check balance тут надо проверить сумму
            source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
            source_account = get_account(source_id, cash)
            selling_asset_code = operation.selling.code if hasattr(operation.selling, 'code') else 'XLM'
            selling_sum = sum(
                float(balance.get('balance')) for balance in source_account['balances']
                if balance.get('asset_code') == selling_asset_code or (
                        selling_asset_code == 'XLM' and 'asset_type' in balance and balance[
                    'asset_type'] == 'native')
            )

            if selling_sum < float(operation.amount):
                result.append(f"<div style=\"color: red;\">Not enough balance to sell {selling_asset_code}! </div>")

            continue
        if type(operation).__name__ == "CreatePassiveSellOffer":
            data_exist = True
            result.append(
                f"    Пассивный офер на продажу {operation.amount} {await asset_to_link(operation.selling)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.buying)}")
            source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
            source_account = get_account(source_id, cash)
            selling_asset_code = operation.selling.code if hasattr(operation.selling, 'code') else 'XLM'
            selling_sum = sum(
                float(balance.get('balance')) for balance in source_account['balances']
                if balance.get('asset_code') == selling_asset_code or (
                        selling_asset_code == 'XLM' and 'asset_type' in balance and balance[
                    'asset_type'] == 'native')
            )

            if selling_sum < float(operation.amount):
                result.append(f"<div style=\"color: red;\">Not enough balance to sell {selling_asset_code}! </div>")
            continue
        if type(operation).__name__ == "ManageBuyOffer":
            data_exist = True
            # check valid asset
            result.append(check_asset(operation.selling, cash))
            result.append(check_asset(operation.buying, cash))

            result.append(
                f"    Офер на покупку {operation.amount} {await asset_to_link(operation.buying)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.selling)}")
            if operation.offer_id != 0:
                result.append(
                    f"    Номер офера <a href=\"https://stellar.expert/explorer/public/offer/{operation.offer_id}\">{operation.offer_id}</a>")

            source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
            source_account = get_account(source_id, cash)
            selling_asset_code = operation.selling.code if hasattr(operation.selling,
                                                                   'code') else 'XLM'  # Учитываем, что XLM не имеет code
            required_amount_to_spend = float(operation.amount) * (operation.price.n / operation.price.d)

            selling_sum = sum(
                float(balance.get('balance')) for balance in source_account['balances']
                if balance.get('asset_code') == selling_asset_code or (
                        selling_asset_code == 'XLM' and 'asset_type' in balance and balance[
                    'asset_type'] == 'native')
            )

            if selling_sum < required_amount_to_spend:
                result.append(
                    f"<div style=\"color: red;\">Not enough {selling_asset_code} to buy! Required: {required_amount_to_spend}, Available: {selling_sum}</div>")

            continue
        if type(operation).__name__ == "PathPaymentStrictSend":
            data_exist = True
            # check valid asset
            result.append(check_asset(operation.send_asset, cash))
            result.append(check_asset(operation.dest_asset, cash))

            result.append(
                f"    Покупка {address_id_to_link(operation.destination.account_id)}, шлем {await asset_to_link(operation.send_asset)} {operation.send_amount} в обмен на {await asset_to_link(operation.dest_asset)} min {operation.dest_min} ")
            continue
        if type(operation).__name__ == "PathPaymentStrictReceive":
            data_exist = True
            # check valid asset
            result.append(check_asset(operation.send_asset, cash))
            result.append(check_asset(operation.dest_asset, cash))
            result.append(
                f"    Продажа {address_id_to_link(operation.destination.account_id)}, Получаем {await asset_to_link(operation.send_asset)} max {operation.send_max} в обмен на {await asset_to_link(operation.dest_asset)} {operation.dest_amount} ")
            continue
        if type(operation).__name__ == "ManageData":
            data_exist = True
            result.append(
                f"    ManageData {operation.data_name} = {operation.data_value} ")
            continue
        if type(operation).__name__ == "SetTrustLineFlags":
            data_exist = True
            result.append(
                f"    Trustor {address_id_to_link(operation.trustor)} for asset {await asset_to_link(operation.asset)}")
            if operation.clear_flags is not None:
                result.append(f"    Clear flags: {operation.clear_flags}")
            if operation.set_flags is not None:
                result.append(f"    Set flags: {operation.set_flags}")
            #  "flags": {
            #   "auth_required": true,
            #   "auth_revocable": true,
            #   "auth_immutable": false,
            #   "auth_clawback_enabled": true
            # },
            if get_account(operation.asset.issuer, cash).get('flags', {}).get('auth_required'):
                pass
            else:
                result.append(f"    <div style=\"color: red;\">issuer {address_id_to_link(operation.asset.issuer)} "
                              f"not need auth </div>")

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
        if type(operation).__name__ == "Clawback":
            data_exist = True
            result.append(
                f"    Возврат {operation.amount} {await asset_to_link(operation.asset)} с аккаунта {address_id_to_link(operation.from_.account_id)}")
            continue
        if type(operation).__name__ == "LiquidityPoolDeposit":
            data_exist = True
            min_price = operation.min_price.n / operation.min_price.d
            max_price = operation.max_price.n / operation.max_price.d
            result.append(
                f"    LiquidityPoolDeposit {pool_id_to_link(operation.liquidity_pool_id)} пополнение {operation.max_amount_a}/{operation.max_amount_b} ограничения цены {min_price}/{max_price}")
            continue
        if type(operation).__name__ == "LiquidityPoolWithdraw":
            data_exist = True
            result.append(
                f"    LiquidityPoolWithdraw {pool_id_to_link(operation.liquidity_pool_id)} вывод {operation.amount} минимум {operation.min_amount_a}/{operation.min_amount_b} ")
            continue
        if type(operation).__name__ in ["PathPaymentStrictSend", "ManageBuyOffer", "ManageSellOffer", "AccountMerge",
                                        "PathPaymentStrictReceive", "ClaimClaimableBalance", "CreateAccount",
                                        "CreateClaimableBalance", "ChangeTrust", "SetOptions", "Payment", "ManageData",
                                        "BeginSponsoringFutureReserves", "EndSponsoringFutureReserves", "Clawback",
                                        "CreatePassiveSellOffer"]:
            continue

        data_exist = True
        result.append(f"Прости хозяин, не понимаю")
        print('bad xdr', idx, operation)
    if data_exist:
        result = [item for item in result if item != '']
        return result
    else:
        return []


def decode_data_value(data_value: str):
    base64_message = data_value
    base64_bytes = base64_message.encode('ascii')
    message_bytes = base64.b64decode(base64_bytes)
    message = message_bytes.decode('ascii')
    return message


def construct_payload(data):
    # prefix 4 to denote application-based signing using 36 bytes
    prefix_selector_bytes = bytes([0] * 35) + bytes([4])

    # standardized namespace prefix for this signing use case
    prefix = "stellar.sep.7 - URI Scheme"

    # variable number of bytes for the prefix + data
    uri_with_prefix_bytes = (prefix + data).encode()

    result = prefix_selector_bytes + uri_with_prefix_bytes
    return result


def uri_sign(data, stellar_private_key):
    # construct the payload
    payload_bytes = construct_payload(data)

    # sign the data
    kp = Keypair.from_secret(stellar_private_key)
    signature_bytes = kp.sign(payload_bytes)

    # encode the signature as base64
    base64_signature = base64.b64encode(signature_bytes).decode()
    # print("base64 signature:", base64_signature)

    # url-encode it
    from urllib.parse import quote
    url_encoded_base64_signature = quote(base64_signature)
    return url_encoded_base64_signature


def add_trust_line_uri(public_key, asset_code, asset_issuer) -> str:
    source_account = Server("https://horizon.stellar.org").load_account(account_id=public_key)

    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=101010
        )
        .append_change_trust_op(Asset(asset_code, asset_issuer))
        .set_timeout(3600)
        .build()
    )
    r1 = stellar_uri.Replacement("sourceAccount", "X", "account on which to create the trustline")
    r2 = stellar_uri.Replacement("seqNum", "Y", "sequence for sourceAccount")
    replacements = [r1, r2]
    t = stellar_uri.TransactionStellarUri(transaction_envelope=transaction, replace=replacements,
                                          origin_domain='eurmtl.me')
    t.sign(config.signing_key.get_secret_value())

    return t.to_uri()


def xdr_to_uri(xdr):
    transaction = TransactionEnvelope.from_xdr(xdr, Network.PUBLIC_NETWORK_PASSPHRASE)
    return stellar_uri.TransactionStellarUri(transaction_envelope=transaction).to_uri()


async def check_user_weight(need_flash=True):
    weight = 0
    if 'user_id' in session:
        user_id = session['user_id']
        user = await mongo.User.find_by_telegram_id(user_id)
        if user is None:
            if need_flash:
                await flash('No such user')
        else:
            public_keys = user.stellar

            url = f'https://horizon.stellar.org/accounts/{main_fund_address}'

            async with aiohttp.ClientSession() as web_session:
                async with web_session.get(url) as response:
                    if response.status == 200:
                        result = await response.json()
                        signers = [signer['key'] for signer in result.get('signers', [])]

                        if any(key in signers for key in public_keys):  # Тут список 20 адресов
                            for signer in result.get('signers', []):
                                if signer['key'] in public_keys:  # Найти первое совпадение
                                    weight = signer['weight']
                                    break
                        else:
                            if need_flash:
                                await flash('User is not a signer')
                    else:
                        if need_flash:
                            await flash('Failed to retrieve account information from Stellar Horizon')
    return weight


async def check_user_in_sign(tr_hash):
    if 'user_id' in session:
        user_id = session['user_id']

        if int(user_id) in (84131737, 3718221):
            return True

        with db_pool() as db_session:
            address = db_session.query(Signers).filter(Signers.tg_id == user_id).first()
            if address is None:
                return False

            # Check if the user has signed this transaction
            signature = db_session.query(Signatures).filter(
                Signatures.transaction_hash == tr_hash,
                Signatures.signer_id == address.id
            ).first()

            if signature:
                return True

    return False


def is_valid_base64(s):
    try:
        base64.b64decode(s)
        return True
    except Exception:
        return False


async def stellar_copy_multi_sign(public_key_from, public_key_for):
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        updated_signers = []
        call = await server.accounts().account_id(public_key_from).call()
        public_key_from_signers = call['signers']
        updated_signers.append({'key': 'threshold',
                                'high_threshold': call['thresholds']['high_threshold'],
                                'low_threshold': call['thresholds']['low_threshold'],
                                'med_threshold': call['thresholds']['med_threshold']})

        public_key_for_signers = (await server.accounts().account_id(public_key_for).call())['signers']

    current_signers = {signer['key']: signer['weight'] for signer in public_key_for_signers}
    new_signers = {signer['key']: signer['weight'] for signer in public_key_from_signers}
    # переносим мастер
    new_signers[public_key_for] = new_signers[public_key_from]
    new_signers.pop(public_key_from)

    # Шаг 1: Добавляем подписантов для удаления (вес 0)
    for signer in current_signers:
        if signer not in new_signers:
            updated_signers.append({'key': signer, 'weight': 0})

    # Шаг 2: Обновляем вес для существующих подписантов
    for signer, weight in current_signers.items():
        if signer in new_signers and new_signers[signer] != weight:
            updated_signers.append({'key': signer, 'weight': new_signers[signer]})

    # Шаг 3: Добавляем новых подписантов
    for signer, weight in new_signers.items():
        if signer not in current_signers:
            updated_signers.append({'key': signer, 'weight': weight})

    return updated_signers


def decode_flags(flag_value):
    flags = TrustLineFlags(0)  # Начальное значение - 0 (нет флагов)
    if flag_value & TrustLineFlags.AUTHORIZED_FLAG:
        flags |= TrustLineFlags.AUTHORIZED_FLAG
    if flag_value & TrustLineFlags.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG:
        flags |= TrustLineFlags.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG
    if flag_value & TrustLineFlags.TRUSTLINE_CLAWBACK_ENABLED_FLAG:
        flags |= TrustLineFlags.TRUSTLINE_CLAWBACK_ENABLED_FLAG
    return flags


async def pay_divs(asset_hold: Asset, total_payment: float):
    async with ServerAsync(horizon_url="https://horizon.stellar.org", client=AiohttpClient()) as server:
        accounts = await server.accounts().for_asset(asset_hold).limit(200).call()
        holders = accounts['_embedded']['records']
        pools = await get_liquidity_pools_for_asset(asset_hold)

        total_assets_hold = 0
        account_assets = {}  # Словарь для хранения суммарных активов по каждому аккаунту

        # Расчет общего количества активов и активов каждого аккаунта, включая доли в пулах ликвидности
        for account in holders:
            account_total_asset = 0  # Суммарное количество активов аккаунта

            for balance in account['balances']:
                # Обработка прямых балансов актива
                if balance['asset_type'] in ['credit_alphanum4', 'credit_alphanum12'] and \
                        balance['asset_code'] == asset_hold.code and \
                        balance['asset_issuer'] == asset_hold.issuer:
                    asset_amount = float(balance['balance'])
                    account_total_asset += asset_amount
                # Обработка долей в пулах ликвидности
                elif balance['asset_type'] == "liquidity_pool_shares":
                    pool_id = balance["liquidity_pool_id"]
                    pool_share = float(balance["balance"])
                    for pool in pools:
                        if pool['id'] == pool_id:
                            asset_amount = float(pool['reserves_dict'].get(f"{asset_hold.code}:{asset_hold.issuer}", 0))
                            total_shares = float(pool['total_shares'])
                            if total_shares > 0 and pool_share > 0:
                                account_total_asset += (pool_share / total_shares) * asset_amount

            # Сохраняем суммарное количество активов аккаунта и обновляем общий счетчик
            account_assets[account['account_id']] = account_total_asset
            total_assets_hold += account_total_asset

        # Расчет выплат, учитывая обновленные балансы
        payments = [{
            'account': account_id,
            'payment': total_payment * (amount / total_assets_hold) if total_assets_hold > 0 else 0
        } for account_id, amount in account_assets.items() if amount > 0]

    return payments


async def get_liquidity_pools_for_asset(asset):
    client = AiohttpClient(request_timeout=3 * 60)

    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=client
    ) as server:
        pools = []
        pools_call_builder = server.liquidity_pools().for_reserves([asset]).limit(200)

        page_records = await pools_call_builder.call()
        while page_records["_embedded"]["records"]:
            for pool in page_records["_embedded"]["records"]:
                # Удаление _links из результатов
                pool.pop('_links', None)

                # Преобразование списка reserves в словарь reserves_dict
                reserves_dict = {reserve['asset']: reserve['amount'] for reserve in pool['reserves']}
                pool['reserves_dict'] = reserves_dict

                # Удаление исходного списка reserves
                pool.pop('reserves', None)

                pools.append(pool)

            page_records = await pools_call_builder.next()
        return pools


async def stellar_manage_data(account_id, data_name, data_value):
    async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        source_account = await server.load_account(account_id=account_id)
        if data_value == '':
            data_value = None

        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                base_fee=101010
            )
            .append_manage_data_op(data_name=data_name, data_value=data_value)
            .set_timeout(10 * 60)
            .build()
        )
        return transaction.to_xdr()


def decode_asset(asset):
    arr = asset.split('-')
    if arr[0] == 'XLM':
        return Asset(arr[0])
    else:
        return Asset(arr[0], arr[1])


async def stellar_build_xdr(data):
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
                                               limit=operation['limit'] if len(operation['limit']) > 0 else None,
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
                if asset['asset_type'] == 'native':
                    asset_path.append(decode_asset(f'XLM'))
                else:
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
        if operation['type'] == 'set_options':
            threshold = operation['threshold']
            if threshold and '/' in str(threshold):
                low, med, high = map(int, threshold.split('/'))
            else:
                low = med = high = int(threshold) if threshold else None

            transaction.append_set_options_op(
                master_weight=int(operation['master']) if operation.get('master') else None,
                med_threshold=med,
                high_threshold=high,
                low_threshold=low,
                home_domain=operation['home'] if operation.get('home') else None,
                source=source_account
            )
        if operation['type'] == 'set_options_signer':
            transaction.append_ed25519_public_key_signer(
                account_id=operation['signerAccount'] if len(operation['signerAccount']) > 55 else None,
                weight=int(operation['weight']) if len(operation['weight']) > 0 else None,
                source=source_account)
        if operation['type'] == 'set_trust_line_flags':
            set_flags_decoded = decode_flags(int(operation['setFlags'])) if len(operation['setFlags']) > 0 else None
            clear_flags_decoded = (decode_flags(int(operation['clearFlags']))
                                   if len(operation['clearFlags']) > 0 else None)

            transaction.append_set_trust_line_flags_op(
                trustor=operation['trustor'],
                asset=decode_asset(operation['asset']),
                set_flags=set_flags_decoded,
                clear_flags=clear_flags_decoded,
                source=source_account)
        if operation['type'] == 'pay_divs':
            # {'account': 'GBVIX6CZ57SHXHGPA4AL7DACNNZX4I2LCKIAA3VQUOGTGWYQYVYSE5TU', 'payment': 60.0}
            for record in await pay_divs(decode_asset(operation['holders']), float(operation['amount'])):
                if round(record['payment'], 7) > 0:
                    transaction.append_payment_op(destination=record['account'],
                                                  asset=decode_asset(operation['asset']),
                                                  amount=float2str(record['payment']),
                                                  source=source_account)
    transaction = transaction.build()
    # transaction.transaction.sequence = int(data['sequence'])
    xdr = transaction.to_xdr()
    return xdr


def add_signer(signer_key, username='FaceLess', user_id=None):
    if username != "FaceLess" and username[0] != '@':
        username = '@' + username

    with db_pool() as db_session:
        db_signer = db_session.query(Signers).filter(Signers.public_key == signer_key).first()
        if db_signer is None:
            hint = Keypair.from_public_key(signer_key).signature_hint().hex()
            db_session.add(Signers(username='FaceLess', public_key=signer_key, tg_id=user_id,
                                   signature_hint=hint))
            db_session.commit()
        else:
            # if user_id and username != 'FaceLess':
            if user_id != db_signer.tg_id or username != db_signer.username:
                db_signer.tg_id = user_id
                db_signer.username = username
                db_session.commit()


async def extract_sources(xdr):
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
                mongo_user = await mongo.User.find_by_stellar_id(signer['key'])
                if mongo_user:
                    add_signer(signer['key'], mongo_user.username, mongo_user.telegram_id)
                else:
                    add_signer(signer['key'])
            sources[source] = {'threshold': threshold, 'signers': signers}
        except:
            sources[source] = {'threshold': 0,
                               'signers': [[source, 1, Keypair.from_public_key(source).signature_hint().hex()]]}
            mongo_user = await mongo.User.find_by_stellar_id(source)
            if mongo_user:
                add_signer(source, mongo_user.username, mongo_user.telegram_id)
            else:
                add_signer(source)
    # print(json.dumps(sources))
    return sources


async def add_transaction(tx_body, tx_description):
    try:
        tr = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        tr_full = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        sources = await extract_sources(tx_body)
    except:
        return False, 'BAD xdr. Can`t load'

    tx_hash = tr.hash_hex()
    tr.signatures.clear()

    with db_pool() as db_session:
        existing_transaction = db_session.query(Transactions).filter(Transactions.hash == tx_hash).first()
        if existing_transaction:
            return True, tx_hash

        new_transaction = Transactions(hash=tx_hash, body=tr.to_xdr(), description=tx_description,
                                       json=json.dumps(sources))
        db_session.add(new_transaction)

        if len(tr_full.signatures) > 0:
            for signature in tr_full.signatures:
                signer = db_session.query(Signers).filter(
                    Signers.signature_hint == signature.signature_hint.hex()).first()
                db_session.add(Signatures(signature_xdr=signature.to_xdr_object().to_xdr(),
                                          signer_id=signer.id if signer else None,
                                          transaction_hash=tx_hash))
        db_session.commit()

    return True, tx_hash


def update_memo_in_xdr(xdr: str, new_memo: str) -> str:
    try:
        transaction = TransactionEnvelope.from_xdr(xdr, Network.PUBLIC_NETWORK_PASSPHRASE)
        transaction.transaction.memo = TextMemo(new_memo)
        return transaction.to_xdr()
    except Exception as e:
        raise Exception(f"Error updating memo: {str(e)}")


if __name__ == '__main__':
    xdr = "AAAAAgAAAAAJk92FjbTLLsK8gty2kiek3bh5GNzHlPtL2Ju3g1BewQAAJ3UCwvFDAAAAHAAAAAEAAAAAAAAAAAAAAABmzaa8AAAAAQAAABBRMzE2IENyZWF0ZSBMQUJSAAAAAQAAAAAAAAAAAAAAAD6PSNQ8NeBFoh7/6169tIn6pjfziFaURDRWU2bQRX+1AAAAAF/2poAAAAAAAAAAAA=="
    print(asyncio.run(add_transaction(xdr, 'True')))
    exit()
    # simple way to find error in editing
    # l = 'https://laboratory.stellar.org/#txbuilder?params=eyJhdHRyaWJ1dGVzIjp7InNvdXJjZUFjY291bnQiOiJHQlRPRjZSTEhSUEc1TlJJVTZNUTdKR01DVjdZSEw1VjMzWVlDNzZZWUc0SlVLQ0pUVVA1REVGSSIsInNlcXVlbmNlIjoiMTg2NzM2MjAxNTQ4NDMxMzc4IiwiZmVlIjoiMTAwMTAiLCJiYXNlRmVlIjoiMTAwIiwibWluRmVlIjoiNTAwMCIsIm1lbW9UeXBlIjoiTUVNT19URVhUIiwibWVtb0NvbnRlbnQiOiJsYWxhbGEifSwiZmVlQnVtcEF0dHJpYnV0ZXMiOnsibWF4RmVlIjoiMTAxMDEifSwib3BlcmF0aW9ucyI6W3siaWQiOjAsImF0dHJpYnV0ZXMiOnsiZGVzdGluYXRpb24iOiJHQUJGUUlLNjNSMk5FVEpNN1Q2NzNFQU1aTjRSSkxMR1AzT0ZVRUpVNVNaVlRHV1VLVUxaSk5MNiIsImFzc2V0Ijp7InR5cGUiOiJjcmVkaXRfYWxwaGFudW00IiwiY29kZSI6IlVTREMiLCJpc3N1ZXIiOiJHQTVaU0VKWUIzN0pSQzVBVkNJQTVNT1A0UkhUTTMzNVgyS0dYM0lIT0pBUFA1UkUzNEs0S1pWTiJ9LCJhbW91bnQiOiIzMDAwMCIsInNvdXJjZUFjY291bnQiOm51bGx9LCJuYW1lIjoicGF5bWVudCJ9XX0%3D&network=public'
    # l = l.split('/')[-1].split('=')[1].split('&')[0]
    # decode_xdr_from_base64(l)
    # e = decode_xdr_to_base64(
    #     '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')
    # decode_xdr_from_base64(e)
    # print(f'https://laboratory.stellar.org/#txbuilder?params={e}&network=public')
    # pass
