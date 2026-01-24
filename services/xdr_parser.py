import asyncio
import base64
import json
import copy
from datetime import datetime, timezone
import jsonpickle
from loguru import logger
from quart import current_app
from stellar_sdk import (
    FeeBumpTransactionEnvelope,
    HashMemo,
    Network,
    NoneMemo,
    TextMemo,
    TransactionEnvelope,
    PathPaymentStrictSend,
    ManageSellOffer,
    Transaction,
    Keypair,
    Asset,
    LiquidityPoolAsset,
    CreatePassiveSellOffer,
    ManageBuyOffer,
    Clawback,
    SetTrustLineFlags,
    TrustLineFlags,
    LiquidityPoolWithdraw,
    LiquidityPoolDeposit,
    StrKey,
)
from stellar_sdk.operation import (
    SetOptions,
    AccountMerge,
    Payment,
    PathPaymentStrictReceive,
    ManageSellOffer,
    ManageBuyOffer,
    CreatePassiveSellOffer,
    ChangeTrust,
    Inflation,
    ManageData,
    BumpSequence,
    CreateClaimableBalance,
)
from stellar_sdk.operation.create_claimable_balance import ClaimPredicateType

from db.sql_models import Transactions
from infrastructure.repositories.transaction_repository import TransactionRepository
from other.grist_cache import grist_cache
from services.stellar_client import (
    get_available_balance_str,
    check_asset,
    get_account,
    get_pool_data,
    float2str,
    get_account_fresh,
)

tools_cash = {}


def get_key_sort(key, idx=1):
    """
    Returns an element from a tuple/list by index for use as a sort key.
    """
    return key[idx]


def decode_xdr_from_base64(xdr):
    import base64

    xdr = xdr.replace("%3D", "=")
    decoded_bytes = base64.urlsafe_b64decode(xdr)
    decoded_str = decoded_bytes.decode("utf-8")
    decoded_json = json.loads(decoded_str)
    # print(decoded_json)


def decode_xdr_to_base64(xdr, return_json=False):
    transaction_envelope = TransactionEnvelope.from_xdr(
        xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
    )
    transaction: Transaction = transaction_envelope.transaction
    new_json = {
        "attributes": {},
        "feeBumpAttributes": {"maxFee": "10101"},
        "operations": [],
    }

    def serialize_asset(asset):
        if isinstance(asset, LiquidityPoolAsset):
            return {
                "type": "liquidity_pool_shares",
                "liquidityPoolId": asset.liquidity_pool_id,
            }
        return asset.to_dict()

    fee = str(int(transaction.fee / len(transaction.operations)))
    new_json["attributes"] = {
        "sourceAccount": transaction.source.account_id,
        "sequence": str(transaction.sequence),
        "fee": fee,
        "baseFee": "100",
        "minFee": "5000",
    }

    if transaction.memo:
        if isinstance(transaction.memo, TextMemo):
            new_json["attributes"]["memoType"] = "MEMO_TEXT"
            new_json["attributes"]["memoContent"] = transaction.memo.memo_text.decode()
        elif isinstance(transaction.memo, HashMemo):
            new_json["attributes"]["memoType"] = "MEMO_HASH"
            new_json["attributes"]["memoContent"] = transaction.memo.memo_hash.hex()

    for op_idx, operation in enumerate(transaction.operations):
        op_name = type(operation).__name__
        op_name = op_name[0].lower() + op_name[1:]
        op_json = {"id": op_idx, "attributes": {}, "name": op_name}

        from stellar_sdk import (
            Payment,
            ChangeTrust,
            CreateAccount,
            SetOptions,
            ManageData,
            ClaimClaimableBalance,
        )

        if isinstance(operation, Payment):
            op_json["attributes"] = {
                "destination": operation.destination.account_id,
                "asset": serialize_asset(operation.asset),
                "amount": float2str(operation.amount),
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, ChangeTrust):
            op_json["attributes"] = {
                "asset": serialize_asset(operation.asset),
                "limit": operation.limit,
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, ManageData):
            op_json["attributes"] = {
                "name": operation.data_name,
                "dataName": operation.data_name,
                "value": operation.data_value.decode()
                if operation.data_value is not None
                else "",
                "dataValue": operation.data_value.decode()
                if operation.data_value is not None
                else "",
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, CreateAccount):
            op_json["attributes"] = {
                "destination": operation.destination,
                "startingBalance": operation.starting_balance,
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, SetTrustLineFlags):
            op_json["attributes"] = {
                "trustor": operation.trustor,
                "asset": serialize_asset(operation.asset),
                "setFlags": operation.set_flags.value if operation.set_flags else None,
                "clearFlags": operation.clear_flags.value
                if operation.clear_flags
                else None,
                "sourceAccount": operation.source.account_id
                if operation.source
                else None,
            }
        elif isinstance(operation, ClaimClaimableBalance):
            op_json["attributes"] = {
                "balanceId": operation.balance_id,
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, ManageSellOffer) or isinstance(
            operation, ManageBuyOffer
        ):
            op_json["attributes"] = {
                "amount": operation.amount,
                "price": operation.price.n / operation.price.d,
                "offerId": operation.offer_id,
                "selling": serialize_asset(operation.selling),
                "buying": serialize_asset(operation.buying),
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, CreatePassiveSellOffer):
            op_json["attributes"] = {
                "amount": operation.amount,
                "price": operation.price.n / operation.price.d,
                "selling": serialize_asset(operation.selling),
                "buying": serialize_asset(operation.buying),
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, Clawback):
            op_json["attributes"] = {
                "amount": operation.amount,
                "asset": operation.asset.to_dict(),
                "from": operation.from_.account_id,
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, SetOptions):
            if operation.signer:
                op_json["name"] = "setOptionsSigner"
                op_json["attributes"] = {
                    "signerAccount": operation.signer.signer_key.encoded_signer_key,
                    "weight": str(operation.signer.weight),
                }
            else:
                if (
                    operation.low_threshold
                    and operation.med_threshold
                    and operation.high_threshold
                ):
                    if (
                        operation.low_threshold
                        == operation.med_threshold
                        == operation.high_threshold
                    ):
                        threshold = operation.low_threshold
                    else:
                        threshold = f"{operation.low_threshold}/{operation.med_threshold}/{operation.high_threshold}"
                else:
                    threshold = None
                op_json["attributes"] = {
                    "sourceAccount": operation.source.account_id
                    if operation.source is not None
                    else None,
                    "master": operation.master_weight,
                    "threshold": threshold,
                    "home": operation.home_domain,
                }
        elif isinstance(operation, PathPaymentStrictSend):
            op_json["attributes"] = {
                "sendAsset": operation.send_asset.to_dict(),
                "destination": operation.destination.account_id,
                "path": operation.path,
                "destMin": operation.dest_min,
                "sendAmount": operation.send_amount,
                "destAsset": operation.dest_asset.to_dict(),
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, LiquidityPoolWithdraw):
            op_json["attributes"] = {
                "liquidityPoolId": operation.liquidity_pool_id,
                "amount": operation.amount,
                "minAmountA": operation.min_amount_a,
                "minAmountB": operation.min_amount_b,
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        elif isinstance(operation, LiquidityPoolDeposit):
            op_json["attributes"] = {
                "liquidityPoolId": operation.liquidity_pool_id,
                "maxAmountA": operation.max_amount_a,
                "maxAmountB": operation.max_amount_b,
                "minPrice": operation.min_price.n / operation.min_price.d,
                "maxPrice": operation.max_price.n / operation.max_price.d,
                "sourceAccount": operation.source.account_id
                if operation.source is not None
                else None,
            }
        else:
            op_json["attributes"] = {"detail": "Unsupported operation type"}
            print("00000000___00000000", type(operation).__name__)

        new_json["operations"].append(op_json)
    if return_json:
        return new_json
    json_data = json.dumps(new_json)
    json_bytes = json_data.encode("utf-8")
    import base64

    encoded_bytes = base64.urlsafe_b64encode(json_bytes)
    encoded_str = encoded_bytes.decode("utf-8")

    return encoded_str


def address_id_to_link(key) -> str:
    start_url = "https://viewer.eurmtl.me/account/"
    return f'<a href="{start_url}{key}" target="_blank">{key[:4] + ".." + key[-4:]}</a>'


def pool_id_to_link(key) -> str:
    start_url = "https://viewer.eurmtl.me/pool/"
    return f'<a href="{start_url}{key}" target="_blank">{key[:4] + ".." + key[-4:]}</a>'


async def asset_to_link(operation_asset) -> str:
    start_url = "https://viewer.eurmtl.me/assets/"
    if operation_asset.code == "XLM":
        return f'<a href="{start_url}{operation_asset.code}" target="_blank">{operation_asset.code}⭐</a>'
    else:
        star = ""
        # add * if we have asset in DB
        key = f"{operation_asset.code}-{operation_asset.issuer}"
        if key in tools_cash:
            asset = tools_cash[key]
            if asset:
                if asset[0]["issuer"] == operation_asset.issuer:
                    star = "⭐"
        else:
            asset = grist_cache.find_by_filter(
                "EURMTL_assets", "code", [operation_asset.code]
            )

            if asset:
                tools_cash[key] = asset
                if asset[0]["issuer"] == operation_asset.issuer:
                    star = "⭐"

        return f'<a href="{start_url}/{operation_asset.code}-{operation_asset.issuer}" target="_blank">{operation_asset.code}{star}</a>'


class SimulatedLedger:
    """
    Simulates the state of the ledger for a single transaction analysis.
    """

    def __init__(self):
        self.accounts = {}  # account_id -> account_data from Horizon
        self.new_assets = set()  # set of "asset_code:asset_issuer"

    async def prefetch_accounts(self, account_ids: set):
        """Fetches initial account states from Horizon in parallel."""
        tasks = [get_account(acc_id) for acc_id in account_ids]
        results = await asyncio.gather(*tasks)
        for acc_id, acc_data in zip(account_ids, results):
            if acc_data and "id" in acc_data:
                self.accounts[acc_id] = copy.deepcopy(acc_data)
            else:
                # Initialize with a default structure if account not found
                self.accounts[acc_id] = {
                    "id": acc_id,
                    "balances": [],
                    "subentry_count": 0,
                    "num_sponsoring": 0,
                    "num_sponsored": 0,
                }

    def get_account(self, account_id: str):
        """Gets account data from the simulation."""
        return self.accounts.get(
            account_id,
            {
                "id": account_id,
                "balances": [],
                "subentry_count": 0,
                "num_sponsoring": 0,
                "num_sponsored": 0,
            },
        )

    def _get_asset_key(self, asset: Asset) -> str:
        """Generates a unique key for an asset."""
        if asset.is_native():
            return "XLM"
        return f"{asset.code}:{asset.issuer}"

    def update_balance(self, account_id: str, asset: Asset, amount_delta: float):
        """Updates the balance of an asset for a given account."""
        account = self.get_account(account_id)
        if "balances" not in account:
            account["balances"] = []

        balance_updated = False
        for balance in account["balances"]:
            if asset.is_native() and balance.get("asset_type") == "native":
                current_balance = float(balance["balance"])
                balance["balance"] = str(current_balance + amount_delta)
                balance_updated = True
                break
            elif (
                not asset.is_native()
                and balance.get("asset_code") == asset.code
                and balance.get("asset_issuer") == asset.issuer
            ):
                current_balance = float(balance["balance"])
                balance["balance"] = str(current_balance + amount_delta)
                balance_updated = True
                break

        if not balance_updated and amount_delta > 0:
            if asset.is_native():
                account["balances"].append(
                    {"asset_type": "native", "balance": str(amount_delta)}
                )
            else:
                account["balances"].append(
                    {
                        "asset_type": asset.type,
                        "asset_code": asset.code,
                        "asset_issuer": asset.issuer,
                        "balance": str(amount_delta),
                    }
                )

    def add_trustline(self, account_id: str, asset: Asset):
        """Adds a trustline to an account."""
        account = self.get_account(account_id)
        if "balances" not in account:
            account["balances"] = []

        if isinstance(asset, LiquidityPoolAsset):
            for balance in account["balances"]:
                if balance.get("liquidity_pool_id") == asset.liquidity_pool_id:
                    return
            account["balances"].append(
                {
                    "balance": "0.0000000",
                    "limit": "922337203685.4775807",
                    "asset_type": "liquidity_pool_shares",
                    "liquidity_pool_id": asset.liquidity_pool_id,
                }
            )
        else:
            for balance in account["balances"]:
                if (
                    not asset.is_native()
                    and balance.get("asset_code") == asset.code
                    and balance.get("asset_issuer") == asset.issuer
                ):
                    return
            account["balances"].append(
                {
                    "balance": "0.0000000",
                    "limit": "922337203685.4775807",
                    "asset_type": asset.type,
                    "asset_code": asset.code,
                    "asset_issuer": asset.issuer,
                }
            )

    def remove_trustline(self, account_id: str, asset: Asset):
        """Removes a trustline from an account."""
        account = self.get_account(account_id)
        if "balances" not in account:
            return

        if isinstance(asset, LiquidityPoolAsset):
            account["balances"] = [
                b
                for b in account["balances"]
                if not (
                    b.get("asset_type") == "liquidity_pool_shares"
                    and b.get("liquidity_pool_id") == asset.liquidity_pool_id
                )
            ]
        else:
            account["balances"] = [
                b
                for b in account["balances"]
                if not (
                    b.get("asset_code") == asset.code
                    and b.get("asset_issuer") == asset.issuer
                )
            ]

    def create_account(self, account_id: str, starting_balance: str):
        """Creates a new account in the simulation."""
        self.accounts[account_id] = {
            "id": account_id,
            "balances": [{"asset_type": "native", "balance": starting_balance}],
            "subentry_count": 0,
            "num_sponsoring": 0,
            "num_sponsored": 0,
        }

    def mark_asset_as_new(self, asset: Asset):
        """Marks an asset as being created within this transaction."""
        if not asset.is_native():
            self.new_assets.add(self._get_asset_key(asset))

    def is_asset_new(self, asset: Asset) -> bool:
        """Checks if an asset was marked as new."""
        if asset.is_native():
            return False
        return self._get_asset_key(asset) in self.new_assets


async def decode_invoke_host_function(operation):
    result = []
    print(jsonpickle.dumps(operation, indent=2))
    try:
        hf = operation.host_function
        result.append(f"      Function Type: {hf.type}")

        if hasattr(hf, "invoke_contract") and hf.invoke_contract:
            ic = hf.invoke_contract

            # Decode contract address
            contract_id_bytes = ic.contract_address.contract_id.hash
            try:
                contract_id_str = StrKey.encode_contract(contract_id_bytes)
            except Exception:
                contract_id_str = contract_id_bytes.hex()
            result.append(f"      Contract: {contract_id_str}")

            # Decode function name
            fn = (
                ic.function_name.sc_symbol.decode("utf-8")
                if hasattr(ic.function_name, "sc_symbol")
                else str(ic.function_name)
            )
            result.append(f"      Function: {fn}")

            # Decode arguments with indexes
            if ic.args:
                result.append("      Arguments:")
                for i, arg in enumerate(ic.args):
                    decoded = decode_scval(arg)
                    result.append(f"        [{i}] {decoded}")
            else:
                result.append("      No arguments")

        elif hasattr(hf, "create_contract") and hf.create_contract:
            cc = hf.create_contract
            result.append("      Create Contract:")
            if cc.contract_id_preimage:
                result.append(
                    f"        Contract ID Preimage: {decode_scval(cc.contract_id_preimage)}"
                )
            if cc.executable:
                result.append(f"        Executable Type: {cc.executable.type}")

        elif hasattr(hf, "install_contract_code") and hf.install_contract_code:
            result.append(
                f"      Install Contract Code (Hash: {hf.install_contract_code.hash.hex()})"
            )

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
    data_exist = False

    def humanize_relative_seconds(total_seconds: int) -> str:
        days, remainder = divmod(int(total_seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days}д")
        if hours:
            parts.append(f"{hours}ч")
        if minutes:
            parts.append(f"{minutes}м")
        if seconds or not parts:
            parts.append(f"{seconds}с")

        return " ".join(parts)

    def format_claim_predicate(predicate, level: int = 0):
        if predicate is None:
            return []

        prefix = "  " * level + "- "
        predicate_type = predicate.claim_predicate_type

        if predicate_type == ClaimPredicateType.CLAIM_PREDICATE_UNCONDITIONAL:
            return [f"{prefix}Без ограничений"]

        if predicate_type == ClaimPredicateType.CLAIM_PREDICATE_BEFORE_ABSOLUTE_TIME:
            if predicate.abs_before is not None:
                claim_until = datetime.fromtimestamp(
                    predicate.abs_before, tz=timezone.utc
                )
                formatted_time = claim_until.strftime("%d.%m.%Y %H:%M:%S")
                return [f"{prefix}Можно получить до {formatted_time} UTC"]
            return [f"{prefix}Ограничение по абсолютному времени не указано"]

        if predicate_type == ClaimPredicateType.CLAIM_PREDICATE_BEFORE_RELATIVE_TIME:
            if predicate.rel_before is not None:
                human_readable = humanize_relative_seconds(predicate.rel_before)
                return [
                    f"{prefix}Можно получить в течение {predicate.rel_before} секунд (~{human_readable}) после создания"
                ]
            return [f"{prefix}Ограничение по относительному времени не указано"]

        if predicate_type == ClaimPredicateType.CLAIM_PREDICATE_AND:
            lines = [f"{prefix}Все перечисленные условия должны выполниться:"]
            if predicate.and_predicates is not None:
                lines.extend(
                    format_claim_predicate(predicate.and_predicates.left, level + 1)
                )
                lines.extend(
                    format_claim_predicate(predicate.and_predicates.right, level + 1)
                )
            return lines

        if predicate_type == ClaimPredicateType.CLAIM_PREDICATE_OR:
            lines = [f"{prefix}Достаточно выполнения любого из условий:"]
            if predicate.or_predicates is not None:
                lines.extend(
                    format_claim_predicate(predicate.or_predicates.left, level + 1)
                )
                lines.extend(
                    format_claim_predicate(predicate.or_predicates.right, level + 1)
                )
            return lines

        if predicate_type == ClaimPredicateType.CLAIM_PREDICATE_NOT:
            lines = [f"{prefix}Следующее условие НЕ должно выполниться:"]
            if predicate.not_predicate is not None:
                lines.extend(format_claim_predicate(predicate.not_predicate, level + 1))
            return lines

        return [f"{prefix}Неизвестный тип условия"]

    if FeeBumpTransactionEnvelope.is_fee_bump_transaction_envelope(xdr):
        fee_transaction = FeeBumpTransactionEnvelope.from_xdr(
            xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
        )
        transaction = fee_transaction.transaction.inner_transaction_envelope
    else:
        transaction = TransactionEnvelope.from_xdr(
            xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
        )
    sequence = transaction.transaction.sequence

    balance_str = await get_available_balance_str(
        transaction.transaction.source.account_id
    )
    result.append(f"Sequence Number {sequence} {balance_str}")

    # Проверяем наличие других транзакций с таким же sequence
    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        exclude_hash = (
            transaction.hash_hex() if hasattr(transaction, "hash_hex") else None
        )
        same_sequence_txs = await repo.get_by_sequence(sequence, exclude_hash)

        if same_sequence_txs:
            links = [
                f'<a href="https://eurmtl.me/sign_tools/{tx.hash}">{tx.description[:10]}...</a>'
                for tx in same_sequence_txs
            ]
            result.append(
                f'<div style="color: orange;">Другие транзакции с этим sequence: {", ".join(links)} </div>'
            )

    account_info = await get_account_fresh(transaction.transaction.source.account_id)
    if "sequence" not in account_info:
        result.append(
            '<div style="color: red;">Аккаунт не найден или не содержит sequence</div>'
        )
        return result
    server_sequence = int(account_info["sequence"])
    expected_sequence = server_sequence + 1

    if sequence != expected_sequence:
        diff = sequence - expected_sequence
        if diff < 0:
            result.append(
                f'<div style="color: red;">Пропущено Sequence {-diff} номеров (current: {sequence}, expected: {expected_sequence})</div>'
            )
        else:
            result.append(
                f'<div style="color: orange;">Номер Sequence больше на {diff} (current: {sequence}, expected: {expected_sequence})</div>'
            )

    if transaction.transaction.fee < 5000:
        result.append(
            f'<div style="color: orange;">Bad Fee {transaction.transaction.fee}! </div>'
        )
    else:
        result.append(f"Fee {transaction.transaction.fee}")

    if (
        transaction.transaction.preconditions
        and transaction.transaction.preconditions.time_bounds
        and transaction.transaction.preconditions.time_bounds.max_time > 0
    ):
        max_time_ts = transaction.transaction.preconditions.time_bounds.max_time
        max_time_dt = datetime.fromtimestamp(max_time_ts, tz=timezone.utc)
        now_dt = datetime.now(timezone.utc)

        human_readable_time = max_time_dt.strftime("%d.%m.%Y %H:%M:%S")

        color = ""
        if max_time_dt < now_dt:
            color = 'style="color: red;"'  # Время прошло
        elif max_time_dt.date() == now_dt.date():
            color = 'style="color: orange;"'  # Время сегодня

        result.append(f"<span {color}>MaxTime ! {human_readable_time} UTC</span>")

    result.append(
        f"Операции с аккаунта {address_id_to_link(transaction.transaction.source.account_id)}"
    )

    memo = transaction.transaction.memo
    if isinstance(memo, NoneMemo):
        result.append("  No memo\n")
    elif isinstance(memo, TextMemo):
        result.append(f'  Memo text: "{memo.memo_text.decode()}"\n')
    elif isinstance(memo, HashMemo):
        result.append(f'  Memo hash (hex): "{memo.memo_hash.hex()}"\n')
    else:
        result.append(f"  Memo is of unsupported type {type(memo).__name__}...\n")

    result.append(f"  Всего {len(transaction.transaction.operations)} операций\n")

    # --- Simulation Setup ---
    all_account_ids = {transaction.transaction.source.account_id}
    for idx, op in enumerate(transaction.transaction.operations):
        if only_op_number is not None and idx != only_op_number:
            continue
        if op.source:
            all_account_ids.add(op.source.account_id)

        # Accounts in 'destination', 'trustor', etc. fields
        if hasattr(op, "destination") and op.destination:
            if isinstance(op.destination, str):
                all_account_ids.add(op.destination)
            elif hasattr(op.destination, "account_id"):
                all_account_ids.add(op.destination.account_id)
        if hasattr(op, "trustor") and op.trustor:
            all_account_ids.add(op.trustor)
        if hasattr(op, "sponsored_id") and op.sponsored_id:
            all_account_ids.add(op.sponsored_id)
        if hasattr(op, "from_") and op.from_:
            all_account_ids.add(op.from_.account_id)
        if isinstance(op, CreateClaimableBalance):
            for claimant in op.claimants:
                all_account_ids.add(claimant.destination)

        # Asset issuers
        assets_to_check = []
        for attr in ["asset", "send_asset", "dest_asset", "selling", "buying"]:
            if hasattr(op, attr):
                asset = getattr(op, attr)
                if asset:
                    assets_to_check.append(asset)

        for asset in assets_to_check:
            if isinstance(asset, LiquidityPoolAsset):
                for pool_asset in [asset.asset_a, asset.asset_b]:
                    if not pool_asset.is_native():
                        all_account_ids.add(pool_asset.issuer)
                continue
            if not asset.is_native():
                all_account_ids.add(asset.issuer)

    simulated_ledger = SimulatedLedger()
    await simulated_ledger.prefetch_accounts(all_account_ids)
    # --- End Simulation Setup ---

    for idx, operation in enumerate(transaction.transaction.operations):
        if only_op_number:
            if idx == 0:
                result.clear()  # clear transaction info
            if idx != only_op_number:
                continue
            if idx > only_op_number:
                break

        result.append(f"Операция {idx} - {type(operation).__name__}")

        op_source_id = (
            operation.source.account_id
            if operation.source
            else transaction.transaction.source.account_id
        )
        balance_str = await get_available_balance_str(op_source_id)
        result.append(
            f"*** для аккаунта {address_id_to_link(op_source_id)} {balance_str}"
        )

        if type(operation).__name__ == "Payment":
            data_exist = True
            dest_id = operation.destination.account_id
            result.append(
                f"    Перевод {operation.amount} {await asset_to_link(operation.asset)} на аккаунт {address_id_to_link(dest_id)}"
            )

            # --- Validation ---
            if not operation.asset.is_native():
                # Check asset existence
                if not simulated_ledger.is_asset_new(operation.asset):
                    check_res = await check_asset(operation.asset)
                    if check_res:
                        result.append(check_res)

                # Check trustline
                if dest_id != operation.asset.issuer:
                    dest_account_sim = simulated_ledger.get_account(dest_id)
                    asset_found = any(
                        b.get("asset_code") == operation.asset.code
                        and b.get("asset_issuer") == operation.asset.issuer
                        for b in dest_account_sim.get("balances", [])
                    )
                    if not asset_found:
                        result.append(
                            f'<div style="color: red;">Error: Trustline for {operation.asset.code} not found on destination account.</div>'
                        )

            # Check balance
            if op_source_id != operation.asset.issuer:
                source_account_sim = simulated_ledger.get_account(op_source_id)
                source_sum = 0
                for b in source_account_sim.get("balances", []):
                    if operation.asset.is_native() and b.get("asset_type") == "native":
                        source_sum = float(b.get("balance", 0))
                        break
                    elif (
                        not operation.asset.is_native()
                        and b.get("asset_code") == operation.asset.code
                        and b.get("asset_issuer") == operation.asset.issuer
                    ):
                        source_sum = float(b.get("balance", 0))
                        break
                if source_sum < float(operation.amount):
                    result.append(
                        f'<div style="color: red;">Error: Not enough balance ({source_sum}) to send {operation.amount}.</div>'
                    )

            # --- State Update ---
            simulated_ledger.update_balance(
                op_source_id, operation.asset, -float(operation.amount)
            )
            simulated_ledger.update_balance(
                dest_id, operation.asset, float(operation.amount)
            )
            continue

        if type(operation).__name__ == "ChangeTrust":
            data_exist = True
            source_id = op_source_id

            # --- Validation & Description ---
            if isinstance(operation.asset, LiquidityPoolAsset):
                if operation.limit == "0":
                    result.append(
                        f"    Закрываем линию доверия к пулу {pool_id_to_link(operation.asset.liquidity_pool_id)} {await asset_to_link(operation.asset.asset_a)}/{await asset_to_link(operation.asset.asset_b)}"
                    )
                else:
                    result.append(
                        f"    Открываем линию доверия к пулу {pool_id_to_link(operation.asset.liquidity_pool_id)} {await asset_to_link(operation.asset.asset_a)}/{await asset_to_link(operation.asset.asset_b)}"
                    )
            else:
                # Check asset existence
                if not simulated_ledger.is_asset_new(operation.asset):
                    check_res = await check_asset(operation.asset)
                    if "not exist" in check_res:
                        result.append(
                            f'<div style="color: orange;">Инфо: Ассет {operation.asset.code} возможно создается в этой транзакции.</div>'
                        )
                        simulated_ledger.mark_asset_as_new(operation.asset)
                    elif check_res:
                        result.append(check_res)

                if operation.asset.issuer == source_id:
                    result.append(
                        f'<div style="color: red;">MELFORMED: You can`t open trustline for yourself!</div>'
                    )

                if operation.limit == "0":
                    result.append(
                        f"    Закрываем линию доверия к токену {await asset_to_link(operation.asset)} от аккаунта {address_id_to_link(operation.asset.issuer)}"
                    )
                else:
                    result.append(
                        f"    Открываем линию доверия к токену {await asset_to_link(operation.asset)} от аккаунта {address_id_to_link(operation.asset.issuer)}"
                    )

            # --- State Update ---
            if operation.limit != "0":
                simulated_ledger.add_trustline(source_id, operation.asset)
            else:
                simulated_ledger.remove_trustline(source_id, operation.asset)
            continue

        if type(operation).__name__ == "CreateAccount":
            data_exist = True
            dest_id = operation.destination
            start_balance = operation.starting_balance
            result.append(
                f"    Создание аккаунта {address_id_to_link(dest_id)} с суммой {start_balance} XLM"
            )

            # --- State Update ---
            simulated_ledger.create_account(dest_id, start_balance)
            simulated_ledger.update_balance(
                op_source_id, Asset.native(), -float(start_balance)
            )
            continue

        # --- Fallback to original logic for other operations ---
        if operation.source:
            pass

        if type(operation).__name__ == "SetOptions":
            data_exist = True
            if operation.signer:
                result.append(
                    f"    Изменяем подписанта {address_id_to_link(operation.signer.signer_key.encoded_signer_key)} новые голоса : {operation.signer.weight}"
                )
            if (
                operation.med_threshold
                or operation.low_threshold
                or operation.high_threshold
            ):
                data_exist = True
                result.append(
                    f"Установка нового требования. Нужно будет {operation.low_threshold}/{operation.med_threshold}/{operation.high_threshold} голосов"
                )
            if operation.home_domain:
                data_exist = True
                result.append(f"Установка нового домена {operation.home_domain}")
            if operation.master_weight is not None:
                data_exist = True
                result.append(f"Установка master_weight {operation.master_weight}")

            continue

        if type(operation).__name__ == "CreateClaimableBalance":
            data_exist = True
            result.append(
                f"    Создаём claimable баланс {operation.amount} {await asset_to_link(operation.asset)}"
            )

            for claimant_idx, claimant in enumerate(operation.claimants, start=1):
                result.append(
                    f"    Получатель {claimant_idx}: {address_id_to_link(claimant.destination)}"
                )

                predicate_lines = format_claim_predicate(claimant.predicate, level=3)
                if predicate_lines:
                    result.append("      Условия получения:")
                    result.extend(predicate_lines)
                else:
                    result.append("      Условия получения: без ограничений")

            continue
        if type(operation).__name__ == "ManageSellOffer":
            data_exist = True
            # check valid asset
            if not simulated_ledger.is_asset_new(operation.selling):
                result.append(await check_asset(operation.selling))
            if not simulated_ledger.is_asset_new(operation.buying):
                result.append(await check_asset(operation.buying))

            result.append(
                f"    Офер на продажу {operation.amount} {await asset_to_link(operation.selling)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.buying)}"
            )
            if operation.offer_id != 0:
                result.append(
                    f'    Номер офера <a href="https://viewer.eurmtl.me/offer/{operation.offer_id}">{operation.offer_id}</a>'
                )
            # check balance тут надо проверить сумму
            source_account = simulated_ledger.get_account(op_source_id)
            selling_asset_code = (
                operation.selling.code if hasattr(operation.selling, "code") else "XLM"
            )
            selling_sum = sum(
                float(balance.get("balance"))
                for balance in source_account["balances"]
                if balance.get("asset_code") == selling_asset_code
                or (
                    selling_asset_code == "XLM"
                    and "asset_type" in balance
                    and balance["asset_type"] == "native"
                )
            )

            selling_asset_issuer = getattr(operation.selling, "issuer", None)
            if (
                selling_sum < float(operation.amount)
                and selling_asset_issuer != op_source_id
            ):
                result.append(
                    f'<div style="color: red;">Error: Not enough balance to sell {selling_asset_code}! </div>'
                )

            continue
        if type(operation).__name__ == "CreatePassiveSellOffer":
            data_exist = True
            result.append(
                f"    Пассивный офер на продажу {operation.amount} {await asset_to_link(operation.selling)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.buying)}"
            )
            source_account = simulated_ledger.get_account(op_source_id)
            selling_asset_code = (
                operation.selling.code if hasattr(operation.selling, "code") else "XLM"
            )
            selling_sum = sum(
                float(balance.get("balance"))
                for balance in source_account["balances"]
                if balance.get("asset_code") == selling_asset_code
                or (
                    selling_asset_code == "XLM"
                    and "asset_type" in balance
                    and balance["asset_type"] == "native"
                )
            )

            selling_asset_issuer = getattr(operation.selling, "issuer", None)
            if (
                selling_sum < float(operation.amount)
                and selling_asset_issuer != op_source_id
            ):
                result.append(
                    f'<div style="color: red;">Error: Not enough balance to sell {selling_asset_code}! </div>'
                )
            continue
        if type(operation).__name__ == "ManageBuyOffer":
            data_exist = True
            # check valid asset
            if not simulated_ledger.is_asset_new(operation.selling):
                result.append(await check_asset(operation.selling))
            if not simulated_ledger.is_asset_new(operation.buying):
                result.append(await check_asset(operation.buying))

            result.append(
                f"    Офер на покупку {operation.amount} {await asset_to_link(operation.buying)} по цене {operation.price.n / operation.price.d} {await asset_to_link(operation.selling)}"
            )
            if operation.offer_id != 0:
                result.append(
                    f'    Номер офера <a href="https://viewer.eurmtl.me/offer/{operation.offer_id}">{operation.offer_id}</a>'
                )

            source_account = simulated_ledger.get_account(op_source_id)
            selling_asset_code = (
                operation.selling.code if hasattr(operation.selling, "code") else "XLM"
            )
            required_amount_to_spend = float(operation.amount) * (
                operation.price.n / operation.price.d
            )

            selling_sum = sum(
                float(balance.get("balance"))
                for balance in source_account["balances"]
                if balance.get("asset_code") == selling_asset_code
                or (
                    selling_asset_code == "XLM"
                    and "asset_type" in balance
                    and balance["asset_type"] == "native"
                )
            )

            selling_asset_issuer = getattr(operation.selling, "issuer", None)
            if (
                selling_sum < required_amount_to_spend
                and selling_asset_issuer != op_source_id
            ):
                result.append(
                    f'<div style="color: red;">Error: Not enough {selling_asset_code} to buy! Required: {required_amount_to_spend}, Available: {selling_sum}</div>'
                )

            continue
        if type(operation).__name__ == "PathPaymentStrictSend":
            data_exist = True
            # check valid asset
            if not simulated_ledger.is_asset_new(operation.send_asset):
                result.append(await check_asset(operation.send_asset))
            if not simulated_ledger.is_asset_new(operation.dest_asset):
                result.append(await check_asset(operation.dest_asset))

            result.append(
                f"    Покупка {address_id_to_link(operation.destination.account_id)}, шлем {await asset_to_link(operation.send_asset)} {operation.send_amount} в обмен на {await asset_to_link(operation.dest_asset)} min {operation.dest_min} "
            )
            continue
        if type(operation).__name__ == "PathPaymentStrictReceive":
            data_exist = True
            # check valid asset
            if not simulated_ledger.is_asset_new(operation.send_asset):
                result.append(await check_asset(operation.send_asset))
            if not simulated_ledger.is_asset_new(operation.dest_asset):
                result.append(await check_asset(operation.dest_asset))
            result.append(
                f"    Продажа {address_id_to_link(operation.destination.account_id)}, Получаем {await asset_to_link(operation.send_asset)} max {operation.send_max} в обмен на {await asset_to_link(operation.dest_asset)} {operation.dest_amount} "
            )
            continue
        if type(operation).__name__ == "ManageData":
            data_exist = True
            result.append(
                f"    ManageData {operation.data_name} = {operation.data_value} "
            )
            continue
        if type(operation).__name__ == "SetTrustLineFlags":
            data_exist = True
            result.append(
                f"    Trustor {address_id_to_link(operation.trustor)} for asset {await asset_to_link(operation.asset)}"
            )
            if operation.clear_flags is not None:
                result.append(f"    Clear flags: {operation.clear_flags}")
            if operation.set_flags is not None:
                result.append(f"    Set flags: {operation.set_flags}")

            issuer_account = simulated_ledger.get_account(operation.asset.issuer)
            if issuer_account.get("flags", {}).get("auth_required"):
                pass
            else:
                result.append(
                    f'    <div style="color: orange;">Warning: issuer {address_id_to_link(operation.asset.issuer)} '
                    f"not need auth </div>"
                )

            continue

        if type(operation).__name__ == "AccountMerge":
            data_exist = True
            result.append(
                f"    Слияние аккаунта c {address_id_to_link(operation.destination.account_id)} "
            )
            continue
        if type(operation).__name__ == "ClaimClaimableBalance":
            data_exist = True
            result.append(
                f"    ClaimClaimableBalance {address_id_to_link(operation.balance_id)}"
            )
            continue
        if type(operation).__name__ == "BumpSequence":
            data_exist = True
            result.append(f"    BumpSequence to {operation.bump_to}")
            continue
        if type(operation).__name__ == "BeginSponsoringFutureReserves":
            data_exist = True
            result.append(
                f"    BeginSponsoringFutureReserves {address_id_to_link(operation.sponsored_id)}"
            )
            continue
        if type(operation).__name__ == "EndSponsoringFutureReserves":
            data_exist = True
            result.append(f"    EndSponsoringFutureReserves")
            continue
        if type(operation).__name__ == "Clawback":
            data_exist = True
            result.append(
                f"    Возврат {operation.amount} {await asset_to_link(operation.asset)} с аккаунта {address_id_to_link(operation.from_.account_id)}"
            )
            continue
        if type(operation).__name__ == "LiquidityPoolDeposit":
            data_exist = True
            min_price = operation.min_price.n / operation.min_price.d
            max_price = operation.max_price.n / operation.max_price.d
            result.append(
                f"    LiquidityPoolDeposit {pool_id_to_link(operation.liquidity_pool_id)} пополнение {operation.max_amount_a}/{operation.max_amount_b} ограничения цены {min_price}/{max_price}"
            )
            pool_data = await get_pool_data(operation.liquidity_pool_id)
            lp_asset = pool_data.get("LiquidityPoolAsset")
            if isinstance(lp_asset, LiquidityPoolAsset):
                source_account_sim = simulated_ledger.get_account(op_source_id)
                assets_to_check = [
                    (lp_asset.asset_a, float(operation.max_amount_a)),
                    (lp_asset.asset_b, float(operation.max_amount_b)),
                ]
                for asset, required_amount in assets_to_check:
                    if op_source_id == asset.issuer:
                        continue
                    if not asset.is_native():
                        has_trustline = any(
                            b.get("asset_code") == asset.code
                            and b.get("asset_issuer") == asset.issuer
                            for b in source_account_sim.get("balances", [])
                        )
                        if not has_trustline:
                            result.append(
                                f'<div style="color: red;">Error: Trustline for {asset.code} not found on source account.</div>'
                            )
                    source_sum = 0.0
                    for b in source_account_sim.get("balances", []):
                        if asset.is_native() and b.get("asset_type") == "native":
                            source_sum = float(b.get("balance", 0))
                            break
                        if (
                            not asset.is_native()
                            and b.get("asset_code") == asset.code
                            and b.get("asset_issuer") == asset.issuer
                        ):
                            source_sum = float(b.get("balance", 0))
                            break
                    if source_sum < required_amount:
                        result.append(
                            f'<div style="color: red;">Error: Not enough balance ({source_sum}) to deposit '
                            f"{required_amount} {await asset_to_link(asset)}.</div>"
                        )
                for asset, required_amount in assets_to_check:
                    if op_source_id == asset.issuer:
                        continue
                    simulated_ledger.update_balance(
                        op_source_id, asset, -required_amount
                    )
            continue
        if type(operation).__name__ == "LiquidityPoolWithdraw":
            data_exist = True
            result.append(
                f"    LiquidityPoolWithdraw {pool_id_to_link(operation.liquidity_pool_id)} вывод {operation.amount} минимум {operation.min_amount_a}/{operation.min_amount_b} "
            )
            pool_data = await get_pool_data(operation.liquidity_pool_id)
            lp_asset = pool_data.get("LiquidityPoolAsset")
            if isinstance(lp_asset, LiquidityPoolAsset):
                simulated_ledger.update_balance(
                    op_source_id, lp_asset.asset_a, float(operation.min_amount_a)
                )
                simulated_ledger.update_balance(
                    op_source_id, lp_asset.asset_b, float(operation.min_amount_b)
                )
            continue
        if type(operation).__name__ == "InvokeHostFunction":
            data_exist = True
            result.append("    InvokeHostFunction Details:")
            # Get detailed function info
            hf_details = await decode_invoke_host_function(operation)
            result.extend(hf_details)
            continue

        if type(operation).__name__ in [
            "PathPaymentStrictSend",
            "ManageBuyOffer",
            "ManageSellOffer",
            "AccountMerge",
            "PathPaymentStrictReceive",
            "ClaimClaimableBalance",
            "CreateAccount",
            "CreateClaimableBalance",
            "ChangeTrust",
            "SetOptions",
            "Payment",
            "ManageData",
            "BeginSponsoringFutureReserves",
            "EndSponsoringFutureReserves",
            "Clawback",
            "CreatePassiveSellOffer",
        ]:
            continue

        data_exist = True
        result.append(f"Прости хозяин, не понимаю")
        print("bad xdr", idx, operation)
    if data_exist:
        result = [item for item in result if item != ""]
        return result
    else:
        return []


def decode_data_value(data_value: str):
    try:
        base64_message = data_value
        base64_bytes = base64_message.encode("utf-8")
        message_bytes = base64.b64decode(base64_bytes)
        message = message_bytes.decode("utf-8")
        return message
    except Exception as ex:
        logger.info(f"decode_data_value error: {ex}")
        return "decode error"


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


def update_memo_in_xdr(xdr: str, new_memo: str) -> str:
    try:
        transaction = TransactionEnvelope.from_xdr(
            xdr, Network.PUBLIC_NETWORK_PASSPHRASE
        )
        transaction.transaction.memo = TextMemo(new_memo)
        return transaction.to_xdr()
    except Exception as e:
        raise Exception(f"Error updating memo: {str(e)}")


def is_valid_base64(s):
    try:
        base64.b64decode(s)
        return True
    except Exception:
        return False
