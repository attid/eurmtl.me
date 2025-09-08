import asyncio
import base64
import json
from datetime import datetime, timezone

import jsonpickle
from loguru import logger
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
    CreatePassiveSellOffer, ManageBuyOffer, Clawback, SetTrustLineFlags, TrustLineFlags, LiquidityPoolWithdraw,
    LiquidityPoolDeposit, LiquidityPoolAsset,
    StrKey
)
from stellar_sdk.operation import SetOptions, AccountMerge, Payment, PathPaymentStrictReceive, PathPaymentStrictSend, ManageSellOffer, ManageBuyOffer, CreatePassiveSellOffer, ChangeTrust, Inflation, ManageData, AllowTrust, BumpSequence
from stellar_sdk.sep import stellar_uri
from other.cache_tools import async_cache_with_ttl
from other.grist_tools import grist_manager, MTLGrist, load_user_from_grist, get_secretaries, load_users_from_grist
from db.sql_models import Signers, Transactions, Signatures
from db.sql_pool import db_pool
from other.config_reader import config
from other.web_tools import http_session_manager

main_fund_address = 'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'
tools_cash = {}


def get_key_sort(key, idx=1):
    """
    Returns an element from a tuple/list by index for use as a sort key.

    Args:
        key: The tuple or list.
        idx: The index of the element to return. Defaults to 1.

    Returns:
        The element at the specified index.
    """
    return key[idx]


async def check_publish_state(tx_hash: str) -> (int, str):
    """
    Checks the status of a transaction on the Horizon network.

    It queries Horizon for the transaction hash and updates its state in the local
    database if it has been successfully submitted.

    Args:
        tx_hash: The hexadecimal hash of the transaction to check.

    Returns:
        A tuple containing a status code and the creation date string.
        Status codes:
        - 0: Not found or error.
        - 1: Found and successful.
        - 10: Found but failed.
    """
    try:
        response = await http_session_manager.get_web_request(
            "GET", f'https://horizon.stellar.org/transactions/{tx_hash}', return_type="json"
        )
        if response.status == 200:
            data = response.data
            date = data['created_at'].replace('T', ' ').replace('Z', '')
            with db_pool() as db_session:
                transaction = db_session.query(Transactions).filter(Transactions.hash == tx_hash).first()
                if transaction and transaction.state != 2:
                    transaction.state = 2
                    db_session.commit()
            if data['successful']:
                return 1, date
            else:
                return 10, date
        else:
            return 0, 'Unknown'
    except Exception as e:
        logger.warning(f"Error checking publish state: {e}")
        return 0, 'Unknown'


def decode_xdr_from_base64(xdr):
    import base64
    xdr = xdr.replace("%3D", "=")
    decoded_bytes = base64.urlsafe_b64decode(xdr)
    decoded_str = decoded_bytes.decode('utf-8')
    # print(decoded_str)
    decoded_json = json.loads(decoded_str)
    # print(decoded_json)


async def get_pool_data(pool_id: str) -> dict:
    """Get current pool data from Horizon including price and reserves"""
    try:
        async with ServerAsync(
                horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            pool = await server.liquidity_pools().liquidity_pool(pool_id).call()
            reserves = pool['reserves']
            if len(reserves) == 2:
                a_amount = float(reserves[0]['amount'])
                b_amount = float(reserves[1]['amount'])
                price = a_amount / b_amount if b_amount > 0 else 1.0

                # Создаем объекты Asset из строк в формате "CODE:ISSUER"
                asset_a_parts = reserves[0]['asset'].split(':')
                asset_b_parts = reserves[1]['asset'].split(':')

                asset_a = Asset(asset_a_parts[0], asset_a_parts[1] if len(asset_a_parts) > 1 else None)
                asset_b = Asset(asset_b_parts[0], asset_b_parts[1] if len(asset_a_parts) > 1 else None)

                return {
                    'price': price,
                    'reserves': reserves,
                    'total_shares': float(pool['total_shares']),
                    'LiquidityPoolAsset': LiquidityPoolAsset(asset_a=asset_a, asset_b=asset_b)
                }
    except Exception as e:
        logger.warning(f"Failed to get pool data: {e}")
    return {
        'price': 1.0,
        'reserves': [{'amount': '0'}, {'amount': '0'}],
        'total_shares': 0,
        'assets': LiquidityPoolAsset(asset_a=Asset('XLM'), asset_b=Asset('XLM'))
    }


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
        elif isinstance(operation, LiquidityPoolWithdraw):
            # noinspection PyTypedDict
            op_json['attributes'] = {'liquidityPoolId': operation.liquidity_pool_id,
                                     'amount': operation.amount,
                                     'minAmountA': operation.min_amount_a,
                                     'minAmountB': operation.min_amount_b,
                                     'sourceAccount': operation.source.account_id if operation.source is not None else None
                                     }
        elif isinstance(operation, LiquidityPoolDeposit):
            # noinspection PyTypedDict
            op_json['attributes'] = {'liquidityPoolId': operation.liquidity_pool_id,
                                     'maxAmountA': operation.max_amount_a,
                                     'maxAmountB': operation.max_amount_b,
                                     'minPrice': operation.min_price.n / operation.min_price.d,
                                     'maxPrice': operation.max_price.n / operation.max_price.d,
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
        star = ''
        # add * if we have asset in DB
        key = f"{operation_asset.code}-{operation_asset.issuer}"
        if key in tools_cash:
            asset = tools_cash[key]
            if asset:
                if asset[0]['issuer'] == operation_asset.issuer:
                    star = '⭐'
        else:
            asset = await grist_manager.load_table_data(
                MTLGrist.EURMTL_assets,
                filter_dict={"code": [operation_asset.code]}
            )

            if asset:
                tools_cash[key] = asset
                if asset[0]['issuer'] == operation_asset.issuer:
                    star = '⭐'

        return f'<a href="{start_url}/{operation_asset.code}-{operation_asset.issuer}" target="_blank">{operation_asset.code}{star}</a>'


async def check_asset(asset, cash: dict):
    try:
        if f"{asset.code}-{asset.issuer}" in cash.keys():
            r = cash[f"{asset.code}-{asset.issuer}"]
        else:
            response = await http_session_manager.get_web_request(
                "GET", f'https://horizon.stellar.org/assets?asset_code={asset.code}&asset_issuer={asset.issuer}',
                return_type="json"
            )
            if response.status == 200:
                r = response.data
            else:
                r = {"_embedded": {"records": []}}
            cash[f"{asset.code}-{asset.issuer}"] = r
        if r["_embedded"]["records"]:
            return ''
    except Exception as e:
        logger.warning(f"Error checking asset: {e}")
        pass
    return f"<div style=\"color: red;\">Asset {asset.code} not exist ! </div>"


async def get_account(account_id, cash):
    if account_id in cash.keys():
        r = cash[account_id]
    else:
        try:
            response = await http_session_manager.get_web_request(
                "GET", 'https://horizon.stellar.org/accounts/' + account_id, return_type="json"
            )
            if response.status == 200:
                r = response.data
                cash[account_id] = r
            else:
                cash[account_id] = {'balances': []}
                r = cash[account_id]
        except Exception as e:
            logger.warning(f"Error getting account {account_id}: {e}")
            cash[account_id] = {'balances': []}
            r = cash[account_id]
    return r


async def get_offers(account_id, cash):
    if f'{account_id}-offers' in cash.keys():
        r = cash[f'{account_id}-offers']
    else:
        try:
            response = await http_session_manager.get_web_request(
                "GET", f'https://horizon.stellar.org/accounts/{account_id}/offers', return_type="json"
            )
            if response.status == 200:
                r = response.data
            else:
                r = {'_embedded': {'records': []}}
            cash[f'{account_id}-offers'] = r
        except Exception as e:
            logger.warning(f"Error getting offers for {account_id}: {e}")
            cash[f'{account_id}-offers'] = {'_embedded': {'records': []}}
            r = cash[f'{account_id}-offers']
    return r


async def decode_invoke_host_function(operation):
    result = []
    print(jsonpickle.dumps(operation, indent=2))
    try:
        hf = operation.host_function
        result.append(f"      Function Type: {hf.type}")

        if hasattr(hf, 'invoke_contract') and hf.invoke_contract:
            ic = hf.invoke_contract

            # Decode contract address
            contract_id_bytes = ic.contract_address.contract_id.hash
            try:
                contract_id_str = StrKey.encode_contract(contract_id_bytes)
            except Exception:
                contract_id_str = contract_id_bytes.hex()
            result.append(f"      Contract: {contract_id_str}")

            # Decode function name
            fn = ic.function_name.sc_symbol.decode('utf-8') if hasattr(ic.function_name, 'sc_symbol') else str(
                ic.function_name)
            result.append(f"      Function: {fn}")

            # Decode arguments with indexes
            if ic.args:
                result.append("      Arguments:")
                for i, arg in enumerate(ic.args):
                    decoded = decode_scval(arg)
                    result.append(f"        [{i}] {decoded}")
            else:
                result.append("      No arguments")

        elif hasattr(hf, 'create_contract') and hf.create_contract:
            cc = hf.create_contract
            result.append("      Create Contract:")
            if cc.contract_id_preimage:
                result.append(f"        Contract ID Preimage: {decode_scval(cc.contract_id_preimage)}")
            if cc.executable:
                result.append(f"        Executable Type: {cc.executable.type}")

        elif hasattr(hf, 'install_contract_code') and hf.install_contract_code:
            result.append(f"      Install Contract Code (Hash: {hf.install_contract_code.hash.hex()})")

    except Exception as e:
        result.append(f"      <error parsing HostFunction: {str(e)}>")

    return result


def decode_scval(val):
    try:
        # Void (пустой SCVal)
        if val.type.value == 0:
            return "Void"

        # Адрес
        if val.type.value == 18:
            addr = val.address
            if addr is None:
                return "None (SCAddress missing)"
            if addr.type.value == 0 and addr.account_id:
                account_id_bytes = addr.account_id.account_id.ed25519.uint256
                return StrKey.encode_ed25519_public_key(account_id_bytes)
            elif addr.type.value == 1 and addr.contract_id:
                return StrKey.encode_contract(addr.contract_id.hash)
            else:
                return "None (SCAddress error)"

        # Символ
        if hasattr(val, "sym") and val.sym:
            return val.sym.sc_symbol.decode("utf-8")

        # Строка
        if hasattr(val, "str") and val.str:
            return val.str

        # Вектор
        if hasattr(val, "vec") and val.vec and val.vec.sc_vec:
            return "[" + ", ".join(decode_scval(v) for v in val.vec.sc_vec) + "]"

        # u128
        if hasattr(val, "u128") and val.u128:
            return str(val.u128.lo.uint64 + (val.u128.hi.uint64 << 64))

        # i128
        if hasattr(val, "i128") and val.i128:
            hi = val.i128.hi.int64
            lo = val.i128.lo.uint64
            return str((hi << 64) + lo)

        return f"None (неизвестный SCVal) (<SCVal [type={val.type.value}, sym={getattr(val.sym, 'sc_symbol', None)}>])"

    except Exception as e:
        return f"<error decoding SCVal: {str(e)}>"


async def decode_xdr_to_text(xdr, only_op_number=None):
    result = []
    cash = {}
    data_exist = False

    if FeeBumpTransactionEnvelope.is_fee_bump_transaction_envelope(xdr):
        fee_transaction = FeeBumpTransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        transaction = fee_transaction.transaction.inner_transaction_envelope
    else:
        transaction = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    sequence = transaction.transaction.sequence
    result.append(f"Sequence Number {sequence}")

    # Проверяем наличие других транзакций с таким же sequence
    with db_pool() as db_session:
        same_sequence_txs = db_session.query(Transactions).filter(
            Transactions.stellar_sequence == sequence,
            Transactions.hash != transaction.hash_hex() if hasattr(transaction, 'hash_hex') else None
        ).all()

        if same_sequence_txs:
            links = [f'<a href="https://eurmtl.me/sign_tools/{tx.hash}">{tx.description[:10]}...</a>'
                     for tx in same_sequence_txs]
            result.append(f"<div style=\"color: orange;\">Другие транзакции с этим sequence: {', '.join(links)} </div>")

    account_info = await get_account(transaction.transaction.source.account_id, cash)
    if 'sequence' not in account_info:
        result.append('<div style="color: red;">Аккаунт не найден или не содержит sequence</div>')
        return result
    server_sequence = int(account_info['sequence'])
    expected_sequence = server_sequence + 1

    if sequence != expected_sequence:
        diff = sequence - expected_sequence
        if diff < 0:
            result.append(
                f"<div style=\"color: red;\">Пропущено Sequence {-diff} номеров (current: {sequence}, expected: {expected_sequence})</div>")
        else:
            result.append(
                f"<div style=\"color: orange;\">Номер Sequence больше на {diff} (current: {sequence}, expected: {expected_sequence})</div>")

    if transaction.transaction.fee < 5000:
        result.append(f"<div style=\"color: orange;\">Bad Fee {transaction.transaction.fee}! </div>")
    else:
        result.append(f"Fee {transaction.transaction.fee}")

    if (transaction.transaction.preconditions and transaction.transaction.preconditions.time_bounds and
            transaction.transaction.preconditions.time_bounds.max_time > 0):
        max_time_ts = transaction.transaction.preconditions.time_bounds.max_time
        max_time_dt = datetime.fromtimestamp(max_time_ts, tz=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        
        human_readable_time = max_time_dt.strftime('%d.%m.%Y %H:%M:%S')
        
        color = ""
        if max_time_dt < now_dt:
            color = 'style="color: red;"' # Время прошло
        elif max_time_dt.date() == now_dt.date():
            color = 'style="color: orange;"' # Время сегодня
            
        result.append(f'<span {color}>MaxTime ! {human_readable_time} UTC</span>')

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
                result.append(await check_asset(operation.asset, cash))
                # check trust line
                if operation.destination.account_id != operation.asset.issuer:
                    destination_account = await get_account(operation.destination.account_id, cash)
                    asset_found = any(
                        balance.get('asset_code') == operation.asset.code for balance in
                        destination_account['balances'])
                    if not asset_found:
                        result.append(f"<div style=\"color: red;\">Asset not found ! </div>")
                source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
                # check balance
                if source_id != operation.asset.issuer:
                    source_account = await get_account(source_id, cash)
                    source_sum = sum(float(balance.get('balance')) for balance in source_account['balances'] if
                                     balance.get('asset_code') == operation.asset.code)
                    if source_sum < float(operation.amount):
                        result.append(f"<div style=\"color: red;\">Not enough balance ! </div>")

                # check sale
                source_sale = await get_offers(source_id, cash)
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
                result.append(
                    f"Установка нового требования. Нужно будет {operation.low_threshold}/{operation.med_threshold}/{operation.high_threshold} голосов")
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
                result.append(await check_asset(operation.asset, cash))
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
            result.append(await check_asset(operation.selling, cash))
            result.append(await check_asset(operation.buying, cash))

            result.append(
                f"    Офер на продажу {operation.amount} {await asset_to_link(operation.selling)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.buying)}")
            if operation.offer_id != 0:
                result.append(
                    f"    Номер офера <a href=\"https://stellar.expert/explorer/public/offer/{operation.offer_id}\">{operation.offer_id}</a>")
            # check balance тут надо проверить сумму
            source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
            source_account = await get_account(source_id, cash)
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
            source_account = await get_account(source_id, cash)
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
            result.append(await check_asset(operation.selling, cash))
            result.append(await check_asset(operation.buying, cash))

            result.append(
                f"    Офер на покупку {operation.amount} {await asset_to_link(operation.buying)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.selling)}")
            if operation.offer_id != 0:
                result.append(
                    f"    Номер офера <a href=\"https://stellar.expert/explorer/public/offer/{operation.offer_id}\">{operation.offer_id}</a>")

            source_id = operation.source.account_id if operation.source else transaction.transaction.source.account_id
            source_account = await get_account(source_id, cash)
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
            result.append(await check_asset(operation.send_asset, cash))
            result.append(await check_asset(operation.dest_asset, cash))

            result.append(
                f"    Покупка {address_id_to_link(operation.destination.account_id)}, шлем {await asset_to_link(operation.send_asset)} {operation.send_amount} в обмен на {await asset_to_link(operation.dest_asset)} min {operation.dest_min} ")
            continue
        if type(operation).__name__ == "PathPaymentStrictReceive":
            data_exist = True
            # check valid asset
            result.append(await check_asset(operation.send_asset, cash))
            result.append(await check_asset(operation.dest_asset, cash))
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
            issuer_account = await get_account(operation.asset.issuer, cash)
            if issuer_account.get('flags', {}).get('auth_required'):
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
        if type(operation).__name__ == "InvokeHostFunction":
            data_exist = True
            result.append("    InvokeHostFunction Details:")
            # Get detailed function info
            hf_details = await decode_invoke_host_function(operation)
            result.extend(hf_details)

            # Add auth info if present
            # if hasattr(operation, 'auth') and operation.auth:
            #     result.append("      Auth Entries:")
            #     for i, auth in enumerate(operation.auth):
            #         result.append(f"        [{i}] {decode_scval(auth)}")

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
    t.sign(config.domain_key.get_secret_value())

    return t.to_uri()


def xdr_to_uri(xdr):
    transaction = TransactionEnvelope.from_xdr(xdr, Network.PUBLIC_NETWORK_PASSPHRASE)
    return stellar_uri.TransactionStellarUri(transaction_envelope=transaction).to_uri()


async def process_xdr_transaction(signed_xdr: str) -> dict:
    """Process XDR transaction from SEP-7 callback"""
    try:
        # Используем основную сеть
        network_passphrase = Network.PUBLIC_NETWORK_PASSPHRASE
        tx_envelope = TransactionEnvelope.from_xdr(signed_xdr, network_passphrase)
        tx = tx_envelope.transaction
        operations = tx.operations

        if len(operations) != 2:
            raise ValueError("Неверное количество операций")

        # Проверка операции 1: manage_data от клиента
        op1 = operations[0]
        expected_key = config.domain + " auth"
        if op1.data_name != expected_key:
            raise ValueError("Неверный ключ в первой операции")

        # Значение nonce хранится в байтах, поэтому преобразуем в строку
        nonce_value = op1.data_value.decode() if op1.data_value is not None else ""

        # Проверка операции 2: manage_data от сервера
        op2 = operations[1]
        if op2.source.account_id != config.domain_account_id or op2.data_name != "web_auth_domain":
            raise ValueError("Неверные данные во второй операции")

        domain_value = op2.data_value.decode() if op2.data_value is not None else ""

        # Возвращаем информацию о транзакции
        return {
            "hash": tx_envelope.hash_hex(),
            "client_address": tx.source.account_id,
            "timestamp": datetime.now().isoformat(),
            "domain": domain_value,
            "nonce": nonce_value
        }
    except Exception as e:
        raise ValueError(f"Ошибка обработки XDR: {str(e)}")


@async_cache_with_ttl(3600)
async def get_fund_signers():
    response = await http_session_manager.get_web_request(
        "GET", 'https://horizon.stellar.org/accounts/' + main_fund_address, return_type="json"
    )
    if response.status == 200:
        data = response.data
        signers = data.get('signers', [])

        if not signers:
            return data

        # Extract all account IDs to fetch them in parallel
        account_ids = [signer['key'] for signer in signers]

        # Load all users from grist in parallel
        users_map = await load_users_from_grist(account_ids)

        # Update telegram_id for each signer
        for signer in signers:
            user = users_map.get(signer['key'])
            signer['telegram_id'] = user.telegram_id if user else 0

        return data

        # if any(key in signers for key in public_keys):  # Тут список 20 адресов
        #     for signer in result.get('signers', []):
        #         if signer['key'] in public_keys:  # Найти первое совпадение
        #             weight = signer['weight']
        #             break


async def check_user_weight(need_flash=True):
    weight = 0
    if 'user_id' in session:
        user_id = session['user_id']
        logger.info(f'check_user_weight user_id {user_id}')
        fund_data = await get_fund_signers()
        if fund_data and 'signers' in fund_data:
            signers = fund_data['signers']
            for signer in signers:
                if int(signer.get('telegram_id', 0)) == int(user_id):
                    weight = signer['weight']
                    break
            if weight == 0 and need_flash:
                await flash('User is not a signer')
        elif need_flash:
            await flash('Failed to retrieve account information')
    return weight


async def check_user_in_sign(tr_hash):
    if 'user_id' in session:
        user_id = session['user_id']

        if int(user_id) in (84131737, 3718221):
            return True

        with db_pool() as db_session:
            # Check if user is owner of transaction
            transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
            if transaction and transaction.owner_id and int(transaction.owner_id) == int(user_id):
                return True

            # Check if user is secretary for transaction account
            secretaries = await get_secretaries()
            if transaction and transaction.source_account in secretaries:
                secretary_users = secretaries[transaction.source_account]
                if any(int(user_id) == int(user) for user in secretary_users):
                    return True

            # Check if the user is a signer
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
    # old_sequence = root_account.sequence
    # Use provided sequence if > 0, otherwise get from horizon
    if 'sequence' in data and int(data['sequence']) > 0:
        root_account.sequence = int(data['sequence']) - 1
        # transaction.set_min_sequence_age()in_sequence_number() = int(data['sequence'])

    transaction = TransactionBuilder(source_account=root_account,
                                     network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
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

        if operation['type'] == 'liquidity_pool_deposit':
            min_price = float(operation['min_price'])
            max_price = float(operation['max_price'])

            if min_price == 0 or max_price == 0:
                pool_data = await get_pool_data(operation['liquidity_pool_id'])
                current_price = pool_data['price']
                if min_price == 0:
                    min_price = current_price * 0.95  # -5%
                if max_price == 0:
                    max_price = current_price * 1.05  # +5%

            transaction.append_liquidity_pool_deposit_op(
                liquidity_pool_id=operation['liquidity_pool_id'],
                max_amount_a=float2str(operation['max_amount_a']),
                max_amount_b=float2str(operation['max_amount_b']),
                min_price=float2str(min_price),
                max_price=float2str(max_price),
                source=source_account
            )
        if operation['type'] == 'liquidity_pool_withdraw':
            min_amount_a = float(operation['min_amount_a'])
            min_amount_b = float(operation['min_amount_b'])

            if min_amount_a == 0 or min_amount_b == 0:
                pool_data = await get_pool_data(operation['liquidity_pool_id'])
                share_ratio = float(operation['amount']) / pool_data['total_shares']

                if min_amount_a == 0:
                    min_amount_a = pool_data['reserves'][0]['amount']
                    min_amount_a = float(min_amount_a) * share_ratio * 0.95
                if min_amount_b == 0:
                    min_amount_b = pool_data['reserves'][1]['amount']
                    min_amount_b = float(min_amount_b) * share_ratio * 0.95

            transaction.append_liquidity_pool_withdraw_op(
                liquidity_pool_id=operation['liquidity_pool_id'],
                amount=float2str(operation['amount']),
                min_amount_a=float2str(min_amount_a),
                min_amount_b=float2str(min_amount_b),
                source=source_account
            )
        if operation['type'] == 'liquidity_pool_trustline':
            pool_data = await get_pool_data(operation['liquidity_pool_id'])
            transaction.append_change_trust_op(asset=pool_data['LiquidityPoolAsset'],
                                               source=source_account,
                                               limit=operation['limit'] if len(operation['limit']) > 0 else None
                                               )
    transaction = transaction.build()
    # transaction.transaction.sequence = int(data['sequence'])
    xdr = transaction.to_xdr()
    return xdr


async def add_signer(signer_key):
    username = 'FaceLess'
    user_id = None

    user = await load_user_from_grist(account_id=signer_key)
    if user:
        username = user.username if user.username else 'FaceLess'
        user_id = user.telegram_id

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


def get_operation_threshold_level(operation) -> str:
    """
    Определяет уровень порога для одной операции.
    Возвращает 'low', 'med' или 'high'.
    """
    op_name = operation.__class__.__name__

    HIGH_THRESHOLD_OPS = {'SetOptions',  # if signers or thresholds
                          'AccountMerge'}

    MEDIUM_THRESHOLD_OPS = {
        'CreateAccount', 'Payment', 'PathPaymentStrictSend', 'PathPaymentStrictReceive',
        'ManageBuyOffer', 'ManageSellOffer', 'CreatePassiveSellOffer',
        'SetOptions',  # if not signers or thresholds
        'ChangeTrust', 'ManageData', 'CreateClaimableBalance',
        'BeginSponsoringFutureReserves', 'EndSponsoringFutureReserves',
        'RevokeSponsorship', 'Clawback', 'ClawbackClaimableBalance',
        'LiquidityPoolDeposit', 'LiquidityPoolWithdraw',
        'InvokeHostFunction', 'ExtendFootprintTTL', 'RestoreFootprint'
    }

    LOW_THRESHOLD_OPS = {
        'BumpSequence',
        'AllowTrust',  # устаревшая операция (deprecated), но всё ещё низкого порога
        'SetTrustLineFlags',  # замена AllowTrust
        'ClaimClaimableBalance'
    }

    if op_name in HIGH_THRESHOLD_OPS:
        if op_name == 'SetOptions':
            # Только определенные изменения в SetOptions требуют высокого порога
            if operation.signer is not None or \
               operation.low_threshold is not None or operation.med_threshold is not None or \
               operation.high_threshold is not None:
                return 'high'
            else:
                # Другие изменения (например, home_domain) имеют средний порог
                return 'med'
        else:  # AccountMerge всегда высокий
            return 'high'

    if op_name in MEDIUM_THRESHOLD_OPS:
        return 'med'

    if op_name in LOW_THRESHOLD_OPS:
        return 'low'

    # Если операция не найдена в списках, по умолчанию используется высокий порог для безопасности
    logger.warning(f"Неизвестный тип операции '{op_name}'. По умолчанию используется высокий порог.")
    return 'high'


async def extract_sources(xdr):
    tr = TransactionEnvelope.from_xdr(xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
    
    # 1. Собираем все уникальные source accounts
    unique_sources = {tr.transaction.source.account_id}
    for op in tr.transaction.operations:
        if op.source:
            unique_sources.add(op.source.account_id)

    # 2. Определяем максимальный уровень порога для каждого source
    source_max_levels = {}
    level_map = {'low': 1, 'med': 2, 'high': 3}
    tx_source_id = tr.transaction.source.account_id

    for source_id in unique_sources:
        max_level_for_source = 'low'
        for op in tr.transaction.operations:
            op_source_id = op.source.account_id if op.source else tx_source_id
            if op_source_id == source_id:
                op_level = get_operation_threshold_level(op)
                if level_map[op_level] > level_map[max_level_for_source]:
                    max_level_for_source = op_level
        source_max_levels[source_id] = max_level_for_source

    # 3. Формируем итоговый результат с правильными порогами
    sources_data = {}
    for source_id, max_level in source_max_levels.items():
        try:
            response = await http_session_manager.get_web_request(
                "GET", f'https://horizon.stellar.org/accounts/{source_id}', return_type="json"
            )
            data = response.data
            account_thresholds = data['thresholds']
            required_threshold_value = account_thresholds[f'{max_level}_threshold']

            signers = []
            for signer in data['signers']:
                signers.append([signer['key'], signer['weight'],
                                Keypair.from_public_key(signer['key']).signature_hint().hex()])
                await add_signer(signer['key'])
            
            sources_data[source_id] = {'threshold': required_threshold_value, 'signers': signers}

        except Exception as e:
            logger.warning(f"Failed to extract source {source_id}: {e}")
            sources_data[source_id] = {'threshold': 0,
                               'signers': [[source_id, 1, Keypair.from_public_key(source_id).signature_hint().hex()]]}
            await add_signer(source_id)
            
    return sources_data


async def update_transaction_sources(transaction: "Transactions") -> bool:
    """Обновляет поле JSON в транзакции свежими данными из Horizon."""
    try:
        # Получаем самую свежую информацию о подписантах и порогах
        fresh_sources = await extract_sources(transaction.body)
        
        # Обновляем поле json
        transaction.json = json.dumps(fresh_sources)
        
        # Используем merge для безопасного обновления объекта в новой сессии
        with db_pool() as db_session:
            db_session.merge(transaction)
            db_session.commit()
        logger.info(f"Successfully updated sources for transaction {transaction.hash}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении источников для транзакции {transaction.hash}: {e}")
        return False


async def add_transaction(tx_body, tx_description):
    try:
        tr = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        tr_full = TransactionEnvelope.from_xdr(tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE)
        sources = await extract_sources(tx_body)
    except Exception as ex:
        logger.info(ex)
        return False, 'BAD xdr. Can`t load'

    tx_hash = tr.hash_hex()
    tr.signatures.clear()

    with db_pool() as db_session:
        existing_transaction = db_session.query(Transactions).filter(Transactions.hash == tx_hash).first()
        if existing_transaction:
            return True, tx_hash

        owner_id = int(session['userdata']['id']) if 'userdata' in session and 'id' in session['userdata'] else None
        new_transaction = Transactions(
            hash=tx_hash,
            body=tr.to_xdr(),
            description=tx_description,
            json=json.dumps(sources),
            stellar_sequence=tr.transaction.sequence,
            source_account=tr.transaction.source.account_id,
            owner_id=owner_id
        )
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


async def test():
    t1 = 'AAAAAgAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAA/eFECGVTNAAAH8AAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAGAAAAAAAAAABc36D3D2ri5jXlKxsZzOmCtNVSwEkrd3ZGm+FLdj7JiIAAAAFYmF0Y2gAAAAAAAADAAAAEAAAAAEAAAABAAAAEgAAAAAAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAAQAAAAAQAAAAMAAAAQAAAAAQAAAAMAAAASAAAAATxgFckVuMNCAaChSQNiWg+um5Jqg6SfCsirbM227W7JAAAADwAAAAVjbGFpbQAAAAAAABAAAAABAAAAAQAAABIAAAAAAAAAANcz8UpgOR0kygfupHRrOkNJ80PsT1V6UvYPnKz1WKyQAAAAEAAAAAEAAAADAAAAEgAAAAGCHvTpTBrgd8We/yRsPiYT6rLaiHgcpyaZMhn2FGN2OgAAAA8AAAAFY2xhaW0AAAAAAAAQAAAAAQAAAAEAAAASAAAAAAAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAAAABAAAAABAAAAAwAAABIAAAABrNVObD55WMdlxCeza7th3GiuhKzd7DyNZ/LfdGYW+dUAAAAPAAAABWNsYWltAAAAAAAAEAAAAAEAAAABAAAAEgAAAAAAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAFzfoPcPauLmNeUrGxnM6YK01VLASSt3dkab4Ut2PsmIgAAAAViYXRjaAAAAAAAAAMAAAAQAAAAAQAAAAEAAAASAAAAAAAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAAAABAAAAABAAAAAwAAABAAAAABAAAAAwAAABIAAAABPGAVyRW4w0IBoKFJA2JaD66bkmqDpJ8KyKtszbbtbskAAAAPAAAABWNsYWltAAAAAAAAEAAAAAEAAAABAAAAEgAAAAAAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAAQAAAAAQAAAAMAAAASAAAAAYIe9OlMGuB3xZ7/JGw+JhPqstqIeBynJpkyGfYUY3Y6AAAADwAAAAVjbGFpbQAAAAAAABAAAAABAAAAAQAAABIAAAAAAAAAANcz8UpgOR0kygfupHRrOkNJ80PsT1V6UvYPnKz1WKyQAAAAEAAAAAEAAAADAAAAEgAAAAGs1U5sPnlYx2XEJ7Nru2HcaK6ErN3sPI1n8t90Zhb51QAAAA8AAAAFY2xhaW0AAAAAAAAQAAAAAQAAAAEAAAASAAAAAAAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAEQAAAAEAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAABSUNFAAAAAAAvI2dJZtbbOdy0TAGiTWWdw8Fm5AJqZio/cnXskAmv/QAAAAYAAAABDW+S3mB4y7cKAiYbxQCEOXnU3k9MAHs38Ger0e/TyV8AAAAQAAAAAQAAAAIAAAAPAAAAB0JhbGFuY2UAAAAAEgAAAAAAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAABAAAABgAAAAENb5LeYHjLtwoCJhvFAIQ5edTeT0wAezfwZ6vR79PJXwAAABQAAAABAAAABgAAAAEiJWfepwCNd51suRAXn4VJc23xiIYO6PyGyjiA0mP4GAAAABQAAAABAAAABgAAAAEohS9owZhIjjRvsSEu1QKQU3Ycwk9FM5LjU5ggGwgl5wAAABQAAAABAAAABgAAAAE8YBXJFbjDQgGgoUkDYloPrpuSaoOknwrIq2zNtu1uyQAAABAAAAABAAAAAwAAAA8AAAAPUmV3YXJkSW52RGF0YVYyAAAAAAMAAAAAAAAABQAAAAAAAABfAAAAAQAAAAYAAAABVCi4nfTpos57F0VW+/5+Krm6FIDOc/fmXYeO1cqQsvMAAAAUAAAAAQAAAAYAAAABcPiBDqRB8xPxhkgBWDKID8BvrEkgmiCEMy36UosRhSkAAAAQAAAAAQAAAAIAAAAPAAAAB0JhbGFuY2UAAAAAEgAAAAAAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAABAAAABgAAAAFw+IEOpEHzE/GGSAFYMogPwG+sSSCaIIQzLfpSixGFKQAAABQAAAABAAAABgAAAAFzfoPcPauLmNeUrGxnM6YK01VLASSt3dkab4Ut2PsmIgAAABQAAAABAAAABgAAAAHdj6Fxj94zLDfNHyI0PruJP/3x0nGz3GaEtzlyf/cdgAAAABAAAAABAAAAAgAAAA8AAAAHQmFsYW5jZQAAAAASAAAAAAAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAAAAAEAAAAGAAAAAd2PoXGP3jMsN80fIjQ+u4k//fHScbPcZoS3OXJ/9x2AAAAAFAAAAAEAAAAHLm8drthyiBrFK/Y3MoB2zYGjtacORlJEU6NUMJx6N4YAAAAHWWrOi4VUNkeFEoIaLg7LApc7G60KQFfcVB/Qyk188DcAAAAHheklNaTCmg8sr9GoIQNe4RkmqmOx7NBFlio5njm4tewAAAAHhmvxAzEB4OrTllSgoWkAyiyW55DV/EPmWXevT8BYOX8AAAAHtUuje3u33WmndZyqnuxw6eE2Fbo7AJ/CPEYmrp3/on8AAAAWAAAAAQAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAAAAAFBUVVBAAAAAFuULlOsM8j9CoDMfBsahdfYOKnEGXeq0Ys68Ff44z3wAAAABgAAAAEohS9owZhIjjRvsSEu1QKQU3Ycwk9FM5LjU5ggGwgl5wAAABAAAAABAAAAAgAAAA8AAAAHQmFsYW5jZQAAAAASAAAAATxgFckVuMNCAaChSQNiWg+um5Jqg6SfCsirbM227W7JAAAAAQAAAAYAAAABKIUvaMGYSI40b7EhLtUCkFN2HMJPRTOS41OYIBsIJecAAAAQAAAAAQAAAAIAAAAPAAAAB0JhbGFuY2UAAAAAEgAAAAGCHvTpTBrgd8We/yRsPiYT6rLaiHgcpyaZMhn2FGN2OgAAAAEAAAAGAAAAASiFL2jBmEiONG+xIS7VApBTdhzCT0UzkuNTmCAbCCXnAAAAEAAAAAEAAAACAAAADwAAAAdCYWxhbmNlAAAAABIAAAABrNVObD55WMdlxCeza7th3GiuhKzd7DyNZ/LfdGYW+dUAAAABAAAABgAAAAE8YBXJFbjDQgGgoUkDYloPrpuSaoOknwrIq2zNtu1uyQAAABAAAAABAAAAAwAAAA8AAAAPUmV3YXJkSW52RGF0YVYyAAAAAAMAAAAAAAAABQAAAAAAAABiAAAAAQAAAAYAAAABPGAVyRW4w0IBoKFJA2JaD66bkmqDpJ8KyKtszbbtbskAAAAQAAAAAQAAAAMAAAAPAAAAD1Jld2FyZEludkRhdGFWMgAAAAADAAAAAQAAAAUAAAAAAAAAAAAAAAEAAAAGAAAAATxgFckVuMNCAaChSQNiWg+um5Jqg6SfCsirbM227W7JAAAAEAAAAAEAAAADAAAADwAAAA9SZXdhcmRJbnZEYXRhVjIAAAAAAwAAAAIAAAAFAAAAAAAAAAAAAAABAAAABgAAAAE8YBXJFbjDQgGgoUkDYloPrpuSaoOknwrIq2zNtu1uyQAAABAAAAABAAAAAgAAAA8AAAAOVXNlclJld2FyZERhdGEAAAAAABIAAAAAAAAAANcz8UpgOR0kygfupHRrOkNJ80PsT1V6UvYPnKz1WKyQAAAAAQAAAAYAAAABPGAVyRW4w0IBoKFJA2JaD66bkmqDpJ8KyKtszbbtbskAAAAQAAAAAQAAAAIAAAAPAAAADldvcmtpbmdCYWxhbmNlAAAAAAASAAAAAAAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAAAAAEAAAAGAAAAATxgFckVuMNCAaChSQNiWg+um5Jqg6SfCsirbM227W7JAAAAFAAAAAEAAAAGAAAAAYIe9OlMGuB3xZ7/JGw+JhPqstqIeBynJpkyGfYUY3Y6AAAAEAAAAAEAAAADAAAADwAAAA9SZXdhcmRJbnZEYXRhVjIAAAAAAwAAAAAAAAAFAAAAAAAAAAwAAAABAAAABgAAAAGCHvTpTBrgd8We/yRsPiYT6rLaiHgcpyaZMhn2FGN2OgAAABAAAAABAAAAAwAAAA8AAAAPUmV3YXJkSW52RGF0YVYyAAAAAAMAAAABAAAABQAAAAAAAAAAAAAAAQAAAAYAAAABgh706Uwa4HfFnv8kbD4mE+qy2oh4HKcmmTIZ9hRjdjoAAAAQAAAAAQAAAAMAAAAPAAAAD1Jld2FyZEludkRhdGFWMgAAAAADAAAAAgAAAAUAAAAAAAAAAAAAAAEAAAAGAAAAAYIe9OlMGuB3xZ7/JGw+JhPqstqIeBynJpkyGfYUY3Y6AAAAEAAAAAEAAAACAAAADwAAAA5Vc2VyUmV3YXJkRGF0YQAAAAAAEgAAAAAAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAABAAAABgAAAAGCHvTpTBrgd8We/yRsPiYT6rLaiHgcpyaZMhn2FGN2OgAAABAAAAABAAAAAgAAAA8AAAAOV29ya2luZ0JhbGFuY2UAAAAAABIAAAAAAAAAANcz8UpgOR0kygfupHRrOkNJ80PsT1V6UvYPnKz1WKyQAAAAAQAAAAYAAAABgh706Uwa4HfFnv8kbD4mE+qy2oh4HKcmmTIZ9hRjdjoAAAAUAAAAAQAAAAYAAAABrNVObD55WMdlxCeza7th3GiuhKzd7DyNZ/LfdGYW+dUAAAAQAAAAAQAAAAMAAAAPAAAAD1Jld2FyZEludkRhdGFWMgAAAAADAAAAAAAAAAUAAAAAAAAAEAAAAAEAAAAGAAAAAazVTmw+eVjHZcQns2u7YdxoroSs3ew8jWfy33RmFvnVAAAAEAAAAAEAAAADAAAADwAAAA9SZXdhcmRJbnZEYXRhVjIAAAAAAwAAAAEAAAAFAAAAAAAAAAAAAAABAAAABgAAAAGs1U5sPnlYx2XEJ7Nru2HcaK6ErN3sPI1n8t90Zhb51QAAABAAAAABAAAAAwAAAA8AAAAPUmV3YXJkSW52RGF0YVYyAAAAAAMAAAACAAAABQAAAAAAAAAAAAAAAQAAAAYAAAABrNVObD55WMdlxCeza7th3GiuhKzd7DyNZ/LfdGYW+dUAAAAQAAAAAQAAAAIAAAAPAAAADlVzZXJSZXdhcmREYXRhAAAAAAASAAAAAAAAAADXM/FKYDkdJMoH7qR0azpDSfND7E9VelL2D5ys9ViskAAAAAEAAAAGAAAAAazVTmw+eVjHZcQns2u7YdxoroSs3ew8jWfy33RmFvnVAAAAEAAAAAEAAAACAAAADwAAAA5Xb3JraW5nQmFsYW5jZQAAAAAAEgAAAAAAAAAA1zPxSmA5HSTKB+6kdGs6Q0nzQ+xPVXpS9g+crPVYrJAAAAABAAAABgAAAAGs1U5sPnlYx2XEJ7Nru2HcaK6ErN3sPI1n8t90Zhb51QAAABQAAAABAkadWAACUdwAAEc8AAAAAAA/d+0AAAAA'
    # t2 = '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'
    a = await decode_xdr_to_text(t1)
    print('\n'.join(a))
    # a = await decode_xdr_to_text(t2)
    # print('\n'.join(a))


async def create_sep7_auth_transaction(domain: str, nonce: str, callback: str) -> str:
    """Создает SEP-7 транзакцию для аутентификации с подменой адреса.

    Args:
        domain: Домен сайта
        nonce: Уникальный идентификатор сессии
        callback: URL для перенаправления пользователя после аутентификации. Должен быть валидным URL.

    Returns:
        URI транзакции с подменой адреса
    """
    # Создаем транзакцию с sequence=0
    source_account = Server("https://horizon.stellar.org").load_account(account_id=main_fund_address)
    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=100
        )
        .append_manage_data_op(
            data_name=f'{config.domain} auth',
            data_value=nonce.encode()
        )
        .append_manage_data_op(
            data_name='web_auth_domain',
            data_value=domain.encode(),
            source=config.domain_account_id
        )
        .set_timeout(300)  # 5 minutes
        .build()
    )

    # Устанавливаем sequence=0
    transaction.transaction.sequence = 101

    # Создаем замену только для адреса
    r1 = stellar_uri.Replacement("sourceAccount", "X", "account to authenticate")
    replacements = [r1]

    # Создаем URI с заменой
    t = stellar_uri.TransactionStellarUri(
        transaction_envelope=transaction,
        replace=replacements,
        origin_domain=config.domain,
        callback=callback
    )

    # Подписываем URI серверным ключом
    t.sign(config.domain_key.get_secret_value())

    # Возвращаем URI вместо XDR
    return t.to_uri()


if __name__ == '__main__':
    asyncio.run(test())

#    xdr = "AAAAAgAAAAAJk92FjbTLLsK8gty2kiek3bh5GNzHlPtL2Ju3g1BewQAAJ3UCwvFDAAAAHAAAAAEAAAAAAAAAAAAAAABmzaa8AAAAAQAAABBRMzE2IENyZWF0ZSBMQUJSAAAAAQAAAAAAAAAAAAAAAD6PSNQ8NeBFoh7/6169tIn6pjfziFaURDRWU2bQRX+1AAAAAF/2poAAAAAAAAAAAA=="
#    print(asyncio.run(add_transaction(xdr, 'True')))
#    exit()
# simple way to find error in editing
# l = 'https://laboratory.stellar.org/#txbuilder?params=eyJhdHRyaWJ1dGVzIjp7InNvdXJjZUFjY291bnQiOiJHQlRPRjZSTEhSUEc1TlJJVTZNUTdKR01DVjdZSEw1VjMzWVlDNzZZWUc0SlVLQ0pUVVA1REVGSSIsInNlcXVlbmNlIjoiMTg2NzM2MjAxNTQ4NDMxMzc4IiwiZmVlIjoiMTAwMTAiLCJiYXNlRmVlIjoiMTAwIiwibWluRmVlIjoiNTAwMCIsIm1lbW9UeXBlIjoiTUVNT19URVhUIiwibWVtb0NvbnRlbnQiOiJsYWxhbGEifSwiZmVlQnVtcEF0dHJpYnV0ZXMiOnsibWF4RmVlIjoiMTAxMDEifSwib3BlcmF0aW9ucyI6W3siaWQiOjAsImF0dHJpYnV0ZXMiOnsiZGVzdGluYXRpb24iOiJHQUJGUUlLNjNSMk5FVEpNN1Q2NzNFQU1aTjRSSkxMR1AzT0ZVRUpVNVNaVlRHV1VLVUxaSk5MNiIsImFzc2V0Ijp7InR5cGUiOiJjcmVkaXRfYWxwaGFudW00IiwiY29kZSI6IlVTREMiLCJpc3N1ZXIiOiJHQTVaU0VKWUIzN0pSQzVBVkNJQTVNT1A0UkhUTTMzNVgyS0dYM0lIT0pBUFA1UkUzNEs0S1pWTiJ9LCJhbW91bnQiOiIzMDAwMCIsInNvdXJjZUFjY291bnQiOm51bGx9LCJuYW1lIjoicGF5bWVudCJ9XX0%3D&network=public'
# l = l.split('/')[-1].split('=')[1].split('&')[0]
# decode_xdr_from_base64(l)
# e = decode_xdr_to_base64(
#     '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')
# decode_xdr_from_base64(e)
# print(f'https://laboratory.stellar.org/#txbuilder?params={e}&network=public')
# pass
