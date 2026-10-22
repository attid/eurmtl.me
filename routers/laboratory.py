import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from loguru import logger

from quart import Blueprint, request, render_template, jsonify, session, current_app
from stellar_sdk import Server
from stellar_sdk.utils import is_valid_hash

from infrastructure.repositories.transaction_repository import TransactionRepository
from other.grist_tools import MTLGrist, grist_manager
from services.xdr_parser import (
    decode_xdr_to_base64,
    is_valid_base64,
    update_memo_in_xdr,
    decode_data_value,
)
from services.stellar_client import stellar_build_xdr, decode_asset, float2str
from other.web_tools import http_session_manager

blueprint = Blueprint("lab", __name__)


@blueprint.route("/laboratory")
@blueprint.route("/lab")
@blueprint.route("/lab/")
async def cmd_laboratory():
    session["return_to"] = request.url
    import_xdr = ""
    tr_hash = request.args.get("import")
    if tr_hash:
        async with current_app.db_pool() as db_session:
            repo = TransactionRepository(db_session)
            if len(tr_hash) == 64:
                transaction = await repo.get_by_hash(tr_hash)
            else:
                transaction = await repo.get_by_uuid(tr_hash)

        if transaction is None:
            return "Transaction not exist =("
        import_xdr = transaction.body

    return await render_template("tabler_laboratory.html", import_xdr=import_xdr)


@blueprint.route("/lab/mtl_accounts", methods=["GET", "POST"])
async def cmd_mtl_accounts():
    if request.method == "GET":
        result = {}
        accounts = await grist_manager.load_table_data(
            MTLGrist.EURMTL_accounts, filter_dict={"need_dropdown": [True]}
        )
        for account in accounts:
            account_id = account["account_id"]  ###
            result[f"{account['description']} {account_id[:4]}..{account_id[-4:]}"] = (
                account_id
            )

        return jsonify(result)
    return None


@blueprint.route("/lab/sequence/<account_id>")
async def cmd_sequence(account_id):
    try:
        response = await http_session_manager.get_web_request(
            "GET", f"https://horizon.stellar.org/accounts/{account_id}"
        )
        if response.status == 200:
            sequence = int(response.data["sequence"]) + 1
        else:
            sequence = 0
    except Exception:
        sequence = 0
    return jsonify({"sequence": str(sequence)})


@blueprint.route("/lab/mtl_assets", methods=["GET", "POST"])
async def cmd_mtl_assets():
    if request.method == "GET":
        result = {}
        assets = await grist_manager.load_table_data(
            MTLGrist.EURMTL_assets, filter_dict={"need_dropdown": [True]}
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


@blueprint.route("/lab/mtl_pools", methods=["GET"])
async def cmd_mtl_pools():
    if request.method == "GET":
        result = {}
        # Используем кеш вместо прямого запроса к Grist
        from other.grist_cache import grist_cache

        all_pools = grist_cache.get_table_data("EURMTL_pools")

        # Фильтруем в памяти
        rows = [pool for pool in all_pools if pool.get("need_dropdown") is True]

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


# --- POST /lab/build_xdr: валидация payload на границе API -----------------
# Sentry #3123: внешний JSON-клиент прислал asset объектом {"code": "XLM"},
# decode_asset() упал с AttributeError ('dict' object has no attribute
# 'split') и роут отдал 500. Объектная форма asset не поддерживается: в
# payload допустима только строка "XLM" или "CODE-ISSUER". Таблица ниже
# перечисляет поля, которые читает stellar_build_xdr(), и их типы. Ошибка
# валидации -> HTTP 400 {"error": ...}; корректный payload проходит дальше
# без изменений, Stellar-логика (services/stellar_client.py) не затронута.
#
# kind:
#   "str"       - строка (сборщик использует len()/.strip()/строковые операции);
#   "asset"     - "XLM" или "CODE-ISSUER";
#   "number"    - число или числовая строка (float2str(), запятая допустима);
#   "float"     - число, которое принимает float() (без запятой и inf/nan);
#   "int"       - int() или числовая строка;
#   "int_str"   - строка, приводимая к int(), пустая строка = нет значения;
#   "threshold" - ""/int/"low/med/high" (как в stellar_build_xdr());
#   "json_path" - JSON-строка с массивом ассетов (swap).
# Суффикс "?" - поле необязательное: отсутствие, null и "" допустимы.
_BUILD_XDR_FIELDS: dict[str, dict[str, str]] = {
    "payment": {"destination": "str", "asset": "asset", "amount": "number"},
    "clawback": {"from": "str", "asset": "asset", "amount": "number"},
    "claim_claimable_balance": {"balanceId": "str"},
    "copy_multi_sign": {"from": "str"},
    "trust_payment": {"destination": "str", "asset": "asset", "amount": "number"},
    "change_trust": {"asset": "asset", "limit": "str"},
    "create_account": {"destination": "str", "startingBalance": "float"},
    "create_claimable_balance": {"asset": "asset", "amount": "number"},
    "sell": {
        "selling": "asset",
        "buying": "asset",
        "amount": "number",
        "price": "number",
        "offer_id": "int",
    },
    "swap": {
        "selling": "asset",
        "buying": "asset",
        "amount": "number",
        "destination": "number",
        "path": "json_path",
    },
    "sell_passive": {
        "selling": "asset",
        "buying": "asset",
        "amount": "number",
        "price": "number",
    },
    "buy": {
        "selling": "asset",
        "buying": "asset",
        "amount": "number",
        "price": "number",
        "offer_id": "int",
    },
    "manage_data": {"data_name": "str", "data_value": "str"},
    "set_options": {"threshold": "threshold", "master": "int?", "home": "str?"},
    "set_options_signer": {"signerAccount": "str", "weight": "int_str"},
    "set_trust_line_flags": {
        "trustor": "str",
        "asset": "asset",
        "setFlags": "int_str",
        "clearFlags": "int_str",
    },
    "bump_sequence": {"bump_to": "int"},
    "begin_sponsoring_future_reserves": {"sponsored_id": "str"},
    "end_sponsoring_future_reserves": {},
    "revoke_sponsorship": {},
    "pay_divs": {"holders": "asset", "asset": "asset", "amount": "float"},
    "liquidity_pool_deposit": {
        "liquidity_pool_id": "str",
        "max_amount_a": "number",
        "max_amount_b": "number",
        "min_price": "float",
        "max_price": "float",
    },
    "liquidity_pool_withdraw": {
        "liquidity_pool_id": "str",
        # amount уточняется в _validate_liquidity_pool_withdraw(): сборщик
        # вызывает float("amount") только при нулевой минимальной сумме.
        "amount": "number",
        "min_amount_a": "float",
        "min_amount_b": "float",
    },
    "liquidity_pool_trustline": {"liquidity_pool_id": "str", "limit": "str"},
}

# Поля revoke_sponsorship зависят от revoke_type; остальные (sourceAccount,
# revoke_type) сборщик читает через .get() и игнорирует при неверном типе,
# поэтому они намеренно не валидируются. Исключение - require_trustline /
# requireTrustline: сборщик приводит значение через int(), см.
# _validate_pay_divs().
_REVOKE_SPONSORSHIP_FIELDS: dict[str, dict[str, str]] = {
    "account": {"revoke_account_id": "str"},
    "trustline": {
        "revoke_trustline_account": "str",
        "revoke_trustline_asset": "asset",
    },
    "data": {"revoke_data_account": "str", "revoke_data_name": "str"},
    "offer": {"revoke_offer_seller": "str", "revoke_offer_id": "int"},
    "claimable_balance": {"revoke_claimable_balance_id": "str"},
    "liquidity_pool": {"revoke_liquidity_pool_id": "str"},
    "signer": {"revoke_signer_account": "str", "revoke_signer_key": "str"},
}

_PREDICATE_TYPES = (
    "unconditional",
    "abs_before",
    "abs_after",
    "rel_before",
    "rel_after",
)


def _is_number(value) -> bool:
    """Число в том виде, в каком его принимает float2str() сборщика."""
    try:
        float2str(value)
        normalized = value.replace(",", ".") if isinstance(value, str) else value
        return math.isfinite(float(normalized))
    except (TypeError, ValueError, OverflowError):
        return False


def _is_float(value) -> bool:
    """Строгое число для полей, где сборщик вызывает float() без нормализации."""
    if isinstance(value, str) and "," in value:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _is_int(value) -> bool:
    try:
        int(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _is_asset(value) -> bool:
    """Проверяет asset той же логикой, что и decode_asset()."""
    try:
        decode_asset(value)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return False
    return True


def _is_threshold(value) -> bool:
    if not value:
        return True
    if isinstance(value, str) and "/" in value:
        parts = value.split("/")
        return len(parts) == 3 and all(_is_int(part) for part in parts)
    return _is_int(value)


def _is_predicate_value(predicate_type: str, value: str) -> bool:
    if predicate_type in ("rel_before", "rel_after"):
        return _is_int(value)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_swap_path(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        path = json.loads(value)
    except ValueError:
        return False
    if not isinstance(path, list):
        return False
    for element in path:
        if not isinstance(element, dict):
            return False
        # Сборщик всегда читает element["asset_type"], поэтому ключ обязателен.
        asset_type = element.get("asset_type")
        if not isinstance(asset_type, str):
            return False
        if asset_type == "native":
            continue
        asset_code = element.get("asset_code")
        asset_issuer = element.get("asset_issuer")
        if not isinstance(asset_code, str) or not isinstance(asset_issuer, str):
            return False
        if not _is_asset(f"{asset_code}-{asset_issuer}"):
            return False
    return True


def _check_payload_field(field_path: str, value, kind: str) -> str | None:
    optional = kind.endswith("?")
    base_kind = kind.rstrip("?")
    if optional and (value is None or value == ""):
        return None

    if base_kind == "str":
        valid, expected = isinstance(value, str), "a string"
    elif base_kind == "asset":
        valid = isinstance(value, str) and _is_asset(value)
        expected = "a string like 'XLM' or 'CODE-ISSUER'"
    elif base_kind == "number":
        valid, expected = _is_number(value), "a number or numeric string"
    elif base_kind == "float":
        valid, expected = _is_float(value), "a number"
    elif base_kind == "int":
        valid, expected = _is_int(value), "an integer or numeric string"
    elif base_kind == "int_str":
        valid = isinstance(value, str) and (value == "" or _is_int(value))
        expected = "an empty or numeric string"
    elif base_kind == "threshold":
        valid, expected = _is_threshold(value), "an integer or 'low/med/high'"
    elif base_kind == "json_path":
        valid = _is_swap_path(value)
        expected = (
            "a JSON array of asset objects, each with a string 'asset_type' "
            "(and 'asset_code' + 'asset_issuer' for non-native)"
        )
    else:  # pragma: no cover - защита от опечатки в таблице
        raise AssertionError(f"Unknown build_xdr validation kind: {kind}")

    if valid:
        return None
    if base_kind == "json_path" and isinstance(value, str):
        # Тип контейнера верный - проблема внутри JSON, он и есть значение.
        return f"{field_path} must be {expected}"
    return f"{field_path} must be {expected} (got {type(value).__name__})"


def _validate_claimants(operation: dict, path: str) -> str | None:
    for index in (1, 2):
        destination = operation.get(f"claimant_{index}_destination", "")
        if not isinstance(destination, str):
            return (
                f"{path}.claimant_{index}_destination must be a string "
                f"(got {type(destination).__name__})"
            )
        if not destination.strip():
            # Сборщик пропускает такого claimant'а, не читая предикат.
            continue
        predicate_type = operation.get(
            f"claimant_{index}_predicate_type", "unconditional"
        )
        if (
            not isinstance(predicate_type, str)
            or predicate_type not in _PREDICATE_TYPES
        ):
            return (
                f"{path}.claimant_{index}_predicate_type must be one of "
                f"{', '.join(_PREDICATE_TYPES)} (got {type(predicate_type).__name__})"
            )
        predicate_value = operation.get(f"claimant_{index}_predicate_value", "")
        if not isinstance(predicate_value, str):
            return (
                f"{path}.claimant_{index}_predicate_value must be a string "
                f"(got {type(predicate_value).__name__})"
            )
        if predicate_type == "unconditional":
            continue
        value = predicate_value.strip()
        if not value:
            return (
                f"{path}.claimant_{index}_predicate_value is required "
                f"for predicate '{predicate_type}'"
            )
        if not _is_predicate_value(predicate_type, value):
            return (
                f"{path}.claimant_{index}_predicate_value must be ISO datetime "
                f"for abs_* or seconds for rel_* (got {value!r})"
            )
    return None


def _validate_liquidity_pool_withdraw(operation: dict, path: str) -> str | None:
    """Уточняет вид поля amount для liquidity_pool_withdraw.

    Сборщик вызывает float(operation["amount"]) только когда одна из
    минимальных сумм равна нулю (расчёт share_ratio); в остальных случаях
    amount идёт через float2str(), который принимает запятую как разделитель.
    Поэтому "1,5" корректен при ненулевых минимумах и недопустим при расчёте.
    """
    try:
        needs_share_ratio = any(
            float(operation[field]) == 0 for field in ("min_amount_a", "min_amount_b")
        )
    except (KeyError, TypeError, ValueError, OverflowError):  # pragma: no cover
        # Недостижимо: тип/наличие min_amount_* уже проверены таблицей выше.
        # Оставлено как защита от изменения порядка проверок.
        return None
    if not needs_share_ratio:
        return None
    return _check_payload_field(f"{path}.amount", operation["amount"], "float")


def _validate_pay_divs(operation: dict, path: str) -> str | None:
    """Проверяет require_trustline / requireTrustline у pay_divs.

    Сборщик (services/stellar_client.py) берёт require_trustline, если ключ
    присутствует, иначе его алиас requireTrustline, и делает int(raw_flag) с
    откатом на True только для TypeError/ValueError. Переполнение там не
    ловится: JSON 1e999 -> inf -> int(inf) -> OverflowError -> 500. Поэтому
    на границе отклоняем только переполнение (400); прочие значения (в т.ч.
    нестроковые и нечисловые, которые сборщик молча превращает в True)
    проходят без изменения поведения. Затенённый алиас не проверяется - он не
    участвует в сборке и не может вызвать OverflowError.
    """
    field_name = (
        "require_trustline" if "require_trustline" in operation else "requireTrustline"
    )
    if field_name not in operation:
        return None
    try:
        int(operation[field_name])
    except OverflowError:
        return (
            f"{path}.{field_name} is out of range for an integer "
            f"(got {operation[field_name]!r})"
        )
    except (TypeError, ValueError):
        # Сборщик откатывается на True - поведение сохранено.
        return None
    return None


def _validate_build_xdr_operation(operation: dict, path: str) -> str | None:
    operation_type = operation.get("type")
    if not isinstance(operation_type, str) or not operation_type:
        return f"{path}.type is required and must be a non-empty string"

    fields = _BUILD_XDR_FIELDS.get(operation_type)
    if fields is None:
        # Неизвестный тип сборщик молча игнорирует - поведение сохранено.
        return None
    if operation_type == "revoke_sponsorship":
        revoke_type = operation.get("revoke_type")
        fields = (
            _REVOKE_SPONSORSHIP_FIELDS.get(revoke_type, {})
            if isinstance(revoke_type, str)
            else {}
        )

    for field_name, kind in fields.items():
        if field_name not in operation:
            if kind.endswith("?"):
                continue
            return f"{path}.{field_name} is required"
        error = _check_payload_field(
            f"{path}.{field_name}", operation[field_name], kind
        )
        if error:
            return error

    if operation_type == "create_claimable_balance":
        return _validate_claimants(operation, path)
    if operation_type == "liquidity_pool_withdraw":
        return _validate_liquidity_pool_withdraw(operation, path)
    if operation_type == "pay_divs":
        return _validate_pay_divs(operation, path)
    return None


def validate_build_xdr_payload(data: dict) -> str | None:
    """Проверяет типы и форматы payload POST /lab/build_xdr.

    Возвращает текст ошибки для HTTP 400 либо None, если payload корректен.
    """
    public_key = data.get("publicKey")
    if not isinstance(public_key, str) or not public_key:
        return "publicKey is required and must be a non-empty string"

    if "sequence" in data:
        error = _check_payload_field("sequence", data["sequence"], "int")
        if error:
            return error

    if data.get("memo_type") == "memo_text" and not isinstance(data.get("memo"), str):
        return "memo is required and must be a string for memo_text"

    operations = data.get("operations")
    if not isinstance(operations, list):
        return "operations is required and must be an array"

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            return (
                f"operations[{index}] must be a JSON object "
                f"(got {type(operation).__name__})"
            )
        error = _validate_build_xdr_operation(operation, f"operations[{index}]")
        if error:
            return error
    return None


@blueprint.route("/lab/build_xdr", methods=["POST"])
async def cmd_build_xdr():
    data = await request.json
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    memo_type = data.get("memo_type", "")
    if memo_type == "memo_hash":
        memo = data.get("memo")
        if not isinstance(memo, str) or not is_valid_hash(memo):
            return jsonify({"error": "Bad memo hash. Must be 64 bytes hex string"})

    error = validate_build_xdr_payload(data)
    if error:
        return jsonify({"error": error}), 400

    xdr = await stellar_build_xdr(data)
    return jsonify({"xdr": xdr})


@blueprint.route("/lab/xdr_to_json", methods=["POST"])
async def cmd_xdr_to_json():
    data = await request.json
    xdr = data.get("xdr")
    try:
        result = decode_xdr_to_base64(xdr, return_json=True)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@blueprint.route("/lab/assets/<account_id>")
async def cmd_assets(account_id):
    result = {"XLM": "XLM"}
    try:
        account = (
            Server(horizon_url="https://horizon.stellar.org")
            .accounts()
            .account_id(account_id)
            .call()
        )
        for balance in account["balances"]:
            asset_code = balance.get("asset_code", "XLM")
            asset_issuer = balance.get("asset_issuer", "XLM")
            result[f"{asset_code}-{asset_issuer[:4]}..{asset_issuer[-4:]}"] = (
                f"{asset_code}-{asset_issuer}"
            )
        assets = (
            Server(horizon_url="https://horizon.stellar.org")
            .assets()
            .for_issuer(account_id)
            .call()
        )
        for asset in assets["_embedded"]["records"]:
            asset_code = asset.get("asset_code", "XLM")
            asset_issuer = asset.get("asset_issuer", "XLM")
            result[f"{asset_code}-{asset_issuer[:4]}..{asset_issuer[-4:]}"] = (
                f"{asset_code}-{asset_issuer}"
            )
    except Exception:
        pass

    return jsonify(result)


@blueprint.route("/lab/claimable_balances/<account_id>")
async def cmd_claimable_balances(account_id):
    result = {}

    def predicate_allows_claim(predicate, created_at_dt):
        now = datetime.now(timezone.utc)

        if predicate is None:
            return False

        if "unconditional" in predicate:
            return predicate["unconditional"] is True

        if "abs_before" in predicate:
            abs_before = predicate["abs_before"]
            if not abs_before:
                return False
            try:
                deadline = datetime.fromisoformat(abs_before.replace("Z", "+00:00"))
            except ValueError:
                return False
            return now < deadline

        if "rel_before" in predicate:
            rel_before_seconds = predicate["rel_before"]
            try:
                seconds = int(rel_before_seconds)
            except (TypeError, ValueError):
                return False
            return now < created_at_dt + timedelta(seconds=seconds)

        if "and" in predicate:
            return all(
                predicate_allows_claim(item, created_at_dt) for item in predicate["and"]
            )

        if "or" in predicate:
            return any(
                predicate_allows_claim(item, created_at_dt) for item in predicate["or"]
            )

        if "not" in predicate:
            return not predicate_allows_claim(predicate["not"], created_at_dt)

        return False

    try:
        response = await http_session_manager.get_web_request(
            "GET",
            f"https://horizon.stellar.org/claimable_balances?claimant={account_id}&limit=200",
            return_type="json",
        )

        if response.status == 200:
            records = response.data.get("_embedded", {}).get("records", [])
            for record in records:
                created_at = record.get("created_at")
                try:
                    created_at_dt = (
                        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if created_at
                        else datetime.now(timezone.utc)
                    )
                except ValueError:
                    created_at_dt = datetime.now(timezone.utc)

                for claimant in record.get("claimants", []):
                    if claimant.get("destination") != account_id:
                        continue

                    predicate = claimant.get("predicate")
                    if not predicate_allows_claim(predicate, created_at_dt):
                        continue

                    balance_id_full = record.get("id", "")
                    if not balance_id_full:
                        continue

                    balance_id_short = balance_id_full.lstrip("0") or balance_id_full

                    asset_descriptor = record.get("asset", "")
                    if asset_descriptor == "native":
                        asset_code = "XLM"
                    else:
                        asset_code = (
                            asset_descriptor.split(":")[0]
                            if ":" in asset_descriptor
                            else asset_descriptor
                        )

                    amount = record.get("amount", "0")
                    label = f"{amount} {asset_code}"
                    result[label] = balance_id_short
    except Exception as ex:
        logger.info(f"Failed to load claimable balances for {account_id}: {ex}")

    return jsonify(result)


@blueprint.route("/lab/data/<account_id>")
async def cmd_data(account_id):
    result = {}
    try:
        account = (
            Server(horizon_url="https://horizon.stellar.org")
            .accounts()
            .account_id(account_id)
            .call()
        )
        for data_name in account.get("data"):
            result[f"{data_name}={decode_data_value(account['data'][data_name])}"] = (
                data_name
            )
    except Exception:
        pass
    result["mtl_delegate if you want delegate your mtl votes"] = "mtl_delegate"
    result["mtl_donate if you want donate"] = "mtl_donate"
    return jsonify(result)


@blueprint.route("/lab/offers/<account_id>")
async def cmd_offers(account_id):
    result = {}
    try:
        account = (
            Server(horizon_url="https://horizon.stellar.org")
            .offers()
            .for_account(account_id)
            .call()
        )
        for record in account["_embedded"]["records"]:
            # Use 'native' for XLM asset code to match frontend logic if needed,
            # but Horizon returns asset_type='native' for XLM.
            # Let's ensure asset codes are present.
            selling_code = record["selling"].get("asset_code", "XLM")
            buying_code = record["buying"].get("asset_code", "XLM")

            label = f"{record['id']} selling {record['amount']} {selling_code} for {buying_code} price {record['price']}"
            result[label] = json.dumps(record)
    except Exception:
        pass
    return jsonify(result)


@blueprint.route("/lab/path/<asset_from>/<asset_for>/<asset_sum>")
async def cmd_path(asset_from, asset_for, asset_sum):
    result = {}
    try:
        account = (
            Server(horizon_url="https://horizon.stellar.org")
            .strict_send_paths(
                source_asset=decode_asset(asset_from),
                source_amount=float2str(asset_sum),
                destination=[decode_asset(asset_for)],
            )
            .call()
        )
        for record in account["_embedded"]["records"]:
            destination_asset_code = (
                record["destination_asset_code"]
                if record.get("destination_asset_code")
                else "XLM"
            )
            result[f"{record['destination_amount']} {destination_asset_code}"] = (
                json.dumps(record["path"])
            )
    except Exception as e:
        logger.info(f"Error: {e}")
    return jsonify(result)


@blueprint.route("/lab/check_balance", methods=["POST"])
async def cmd_check_balance():
    data = await request.json
    account_id = data.get("account_id")
    asset_str = data.get("asset")

    if not account_id or len(account_id) != 56:
        return jsonify({"error": "Invalid account ID"}), 400
    if not asset_str:
        return jsonify({"error": "Invalid asset"}), 400

    # Check if issuer (Asset format: CODE-ISSUER)
    if "-" in asset_str:
        try:
            code, issuer = asset_str.split("-")
            if issuer == account_id:
                return jsonify({"balance": "Unlimited", "is_issuer": True})
        except Exception:
            pass

    try:
        account = (
            Server(horizon_url="https://horizon.stellar.org")
            .accounts()
            .account_id(account_id)
            .call()
        )

        balance_val = "0"

        if asset_str == "XLM":
            for bal in account["balances"]:
                if bal["asset_type"] == "native":
                    balance_val = bal["balance"]
                    break
        elif "-" in asset_str:
            code, issuer = asset_str.split("-")
            for bal in account["balances"]:
                if bal.get("asset_code") == code and bal.get("asset_issuer") == issuer:
                    balance_val = bal["balance"]
                    break
        elif len(asset_str) == 64:  # Liquidity Pool ID
            for bal in account["balances"]:
                if (
                    bal.get("asset_type") == "liquidity_pool_shares"
                    and bal.get("liquidity_pool_id") == asset_str
                ):
                    balance_val = bal["balance"]
                    break

        return jsonify({"balance": balance_val})

    except Exception as e:
        logger.warning(f"Error fetching balance: {e}")
        return jsonify({"error": "Failed to fetch account"}), 400


@blueprint.route("/lab/update_memo", methods=["POST"])
async def lab_update_memo():
    data = await request.json
    xdr = data.get("xdr")
    new_memo = data.get("memo")

    if not xdr or not is_valid_base64(xdr):
        return jsonify({"error": "Invalid or missing XDR"}), 400

    if not new_memo or len(new_memo) < 3 or len(new_memo.encode("utf-8")) > 28:
        return jsonify(
            {"error": "Invalid memo length. Must be between 3 characters and 28 bytes"}
        ), 400

    if not new_memo.isprintable():
        return jsonify({"error": "Memo must contain only printable characters"}), 400

    try:
        new_xdr = update_memo_in_xdr(xdr, new_memo)
        return jsonify({"success": True, "xdr": new_xdr}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to update memo: {str(e)}"}), 400


if __name__ == "__main__":
    asyncio.run(
        cmd_path(
            "XLM",
            "BTCMTL-GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
            "150",
        )
    )
