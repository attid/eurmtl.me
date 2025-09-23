import asyncio
import json
from datetime import datetime, timedelta, timezone
from loguru import logger

from quart import Blueprint, request, render_template, jsonify, session
from stellar_sdk import Server
from stellar_sdk.utils import is_valid_hash

from db.sql_models import Transactions
from db.sql_pool import db_pool
from other.grist_tools import MTLGrist, grist_manager
from other.stellar_tools import (decode_xdr_to_base64, stellar_build_xdr, decode_asset,
                                 is_valid_base64, update_memo_in_xdr, decode_data_value, float2str)
from other.web_tools import http_session_manager

blueprint = Blueprint('lab', __name__)


@blueprint.route('/laboratory')
@blueprint.route('/lab')
@blueprint.route('/lab/')
async def cmd_laboratory():
    session['return_to'] = request.url
    import_xdr = ''
    tr_hash = request.args.get('import')
    if tr_hash:
        with db_pool() as db_session:
            if len(tr_hash) == 64:
                transaction = db_session.query(Transactions).filter(Transactions.hash == tr_hash).first()
            else:
                transaction = db_session.query(Transactions).filter(Transactions.uuid == tr_hash).first()

        if transaction is None:
            return 'Transaction not exist =('
        import_xdr = transaction.body

    return await render_template('tabler_laboratory.html', import_xdr=import_xdr)


@blueprint.route('/lab/mtl_accounts', methods=['GET', 'POST'])
async def cmd_mtl_accounts():
    if request.method == 'GET':
        result = {}
        accounts = await grist_manager.load_table_data(
            MTLGrist.EURMTL_accounts,
            filter_dict={"need_dropdown": [True]}
        )
        for account in accounts:
            account_id = account["account_id"]  ###
            result[f"{account['description']} {account_id[:4]}..{account_id[-4:]}"] = account_id

        return jsonify(result)
    return None


@blueprint.route('/lab/sequence/<account_id>')
async def cmd_sequence(account_id):
    try:
        response = await http_session_manager.get_web_request('GET', f'https://horizon.stellar.org/accounts/{account_id}')
        if response.status == 200:
            sequence = int(response.data['sequence']) + 1
        else:
            sequence = 0
    except:
        sequence = 0
    return jsonify({'sequence': str(sequence)})


@blueprint.route('/lab/mtl_assets', methods=['GET', 'POST'])
async def cmd_mtl_assets():
    if request.method == 'GET':
        result = {}
        assets = await grist_manager.load_table_data(
            MTLGrist.EURMTL_assets,
            filter_dict={"need_dropdown": [True]}
        )

        for asset in assets:
            asset_code = asset["code"]
            asset_issuer = asset["issuer"]

            # Формируем ключ и значение как в исходной функции
            key = f"{asset_code}-{asset_issuer[:4]}..{asset_issuer[-4:]}"
            value = f"{asset_code}-{asset_issuer}"
            result[key] = value

        # Добавляем XLM как отдельный элемент
        result["XLM"] = "XLM"

        return jsonify(result)
    return None


@blueprint.route('/lab/mtl_pools', methods=['GET'])
async def cmd_mtl_pools():
    if request.method == 'GET':
        result = {}
        # Используем кеш вместо прямого запроса к Grist
        from other.grist_cache import grist_cache
        all_pools = grist_cache.get_table_data('EURMTL_pools')
        
        # Фильтруем в памяти
        rows = [pool for pool in all_pools if pool.get('need_dropdown') is True]

        for row in rows:
            print(row)
            info = row["info"]
            pool_id = row["pool_id"]

            # Формируем ключ и значение как в исходной функции
            key = f"{info}"
            value = f"{pool_id}"
            result[key] = value

        return jsonify(result)
    return None


@blueprint.route('/lab/build_xdr', methods=['POST'])
async def cmd_build_xdr():
    data = await request.json
    if data['memo_type'] == 'memo_hash':
        if not is_valid_hash(data['memo']):
            return jsonify({'error': 'Bad memo hash. Must be 64 bytes hex string'})

    xdr = await stellar_build_xdr(data)
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


@blueprint.route('/lab/claimable_balances/<account_id>')
async def cmd_claimable_balances(account_id):
    result = {}

    def predicate_allows_claim(predicate, created_at_dt):
        now = datetime.now(timezone.utc)

        if predicate is None:
            return False

        if 'unconditional' in predicate:
            return predicate['unconditional'] is True

        if 'abs_before' in predicate:
            abs_before = predicate['abs_before']
            if not abs_before:
                return False
            try:
                deadline = datetime.fromisoformat(abs_before.replace('Z', '+00:00'))
            except ValueError:
                return False
            return now < deadline

        if 'rel_before' in predicate:
            rel_before_seconds = predicate['rel_before']
            try:
                seconds = int(rel_before_seconds)
            except (TypeError, ValueError):
                return False
            return now < created_at_dt + timedelta(seconds=seconds)

        if 'and' in predicate:
            return all(predicate_allows_claim(item, created_at_dt) for item in predicate['and'])

        if 'or' in predicate:
            return any(predicate_allows_claim(item, created_at_dt) for item in predicate['or'])

        if 'not' in predicate:
            return not predicate_allows_claim(predicate['not'], created_at_dt)

        return False

    try:
        response = await http_session_manager.get_web_request(
            'GET',
            f'https://horizon.stellar.org/claimable_balances?claimant={account_id}&limit=200',
            return_type="json"
        )

        if response.status == 200:
            records = response.data.get('_embedded', {}).get('records', [])
            for record in records:
                created_at = record.get('created_at')
                try:
                    created_at_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00')) if created_at else datetime.now(timezone.utc)
                except ValueError:
                    created_at_dt = datetime.now(timezone.utc)

                for claimant in record.get('claimants', []):
                    if claimant.get('destination') != account_id:
                        continue

                    predicate = claimant.get('predicate')
                    if not predicate_allows_claim(predicate, created_at_dt):
                        continue

                    balance_id_full = record.get('id', '')
                    if not balance_id_full:
                        continue

                    balance_id_short = balance_id_full.lstrip('0') or balance_id_full

                    asset_descriptor = record.get('asset', '')
                    if asset_descriptor == 'native':
                        asset_code = 'XLM'
                    else:
                        asset_code = asset_descriptor.split(':')[0] if ':' in asset_descriptor else asset_descriptor

                    amount = record.get('amount', '0')
                    label = f"{amount} {asset_code}"
                    result[label] = balance_id_short
    except Exception as ex:
        logger.info(f"Failed to load claimable balances for {account_id}: {ex}")

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
            destination_asset_code = record['destination_asset_code'] if record.get('destination_asset_code') else 'XLM'
            result[f"{record['destination_amount']} {destination_asset_code}"] = json.dumps(record['path'])
    except Exception as e:
        logger.info(f"Error: {e}")
    return jsonify(result)


@blueprint.route('/lab/update_memo', methods=['POST'])
async def lab_update_memo():
    data = await request.json
    xdr = data.get("xdr")
    new_memo = data.get("memo")

    if not xdr or not is_valid_base64(xdr):
        return jsonify({"error": "Invalid or missing XDR"}), 400

    if not new_memo or len(new_memo) < 3 or len(new_memo) > 28:
        return jsonify({"error": "Invalid memo length. Must be between 3 and 28 characters"}), 400

    if not new_memo.isascii():
        return jsonify({"error": "Memo must contain only ASCII characters"}), 400

    try:
        new_xdr = update_memo_in_xdr(xdr, new_memo)
        return jsonify({
            "success": True,
            "xdr": new_xdr
        }), 200
    except Exception as e:
        return jsonify({
            "error": f"Failed to update memo: {str(e)}"
        }), 400


if __name__ == '__main__':
    asyncio.run(cmd_path('XLM', 'BTCMTL-GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V', '150'))
