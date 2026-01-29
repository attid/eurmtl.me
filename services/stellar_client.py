import asyncio
import base64
import json
from datetime import datetime
from loguru import logger
from quart import session, flash, current_app
from stellar_sdk import (
    Keypair,
    ServerAsync,
    AiohttpClient,
    Asset,
    TransactionBuilder,
    Network,
    TransactionEnvelope,
    LiquidityPoolAsset,
    TrustLineFlags,
)
from stellar_sdk.operation.create_claimable_balance import Claimant, ClaimPredicate
from stellar_sdk.sep import stellar_uri
from sqlalchemy import select

from other.cache_tools import async_cache_with_ttl
from other.grist_cache import grist_cache
from other.grist_tools import (
    get_secretaries,
    load_users_from_grist,
    load_user_from_grist,
)
from other.web_tools import http_session_manager
from other.config_reader import config
from db.sql_models import Signers, Transactions, Signatures
from infrastructure.repositories.transaction_repository import TransactionRepository

main_fund_address = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
tools_cash = {}


def float2str(f) -> str:
    if isinstance(f, str):
        f = f.replace(",", ".")
        f = float(f)
    s = "%.7f" % f
    while len(s) > 1 and s[-1] in ("0", "."):
        l = s[-1]
        s = s[0:-1]
        if l == ".":
            break
    return s


async def check_publish_state(tx_hash: str) -> tuple[int, str]:
    """
    Checks the status of a transaction on the Horizon network.
    """
    try:
        response = await http_session_manager.get_web_request(
            "GET",
            f"https://horizon.stellar.org/transactions/{tx_hash}",
            return_type="json",
        )
        if response.status == 200:
            data = response.data
            date = data["created_at"].replace("T", " ").replace("Z", "")
            async with current_app.db_pool() as db_session:
                repo = TransactionRepository(db_session)
                transaction = await repo.get_by_hash(tx_hash)
                if transaction and transaction.state != 2:
                    transaction.state = 2
                    await repo.commit()
            if data["successful"]:
                return 1, date
            else:
                return 10, date
        else:
            return 0, "Unknown"
    except Exception as e:
        logger.warning(f"Error checking publish state: {e}")
        return 0, "Unknown"


async def get_pool_data(pool_id: str) -> dict:
    """Get current pool data from Horizon including price and reserves"""
    try:
        async with ServerAsync(
            horizon_url="https://horizon.stellar.org", client=AiohttpClient()
        ) as server:
            pool = await server.liquidity_pools().liquidity_pool(pool_id).call()
            reserves = pool["reserves"]
            if len(reserves) == 2:
                a_amount = float(reserves[0]["amount"])
                b_amount = float(reserves[1]["amount"])
                price = a_amount / b_amount if b_amount > 0 else 1.0

                # Создаем объекты Asset из строк в формате "CODE:ISSUER"
                asset_a_parts = reserves[0]["asset"].split(":")
                asset_b_parts = reserves[1]["asset"].split(":")

                asset_a = Asset(
                    asset_a_parts[0],
                    asset_a_parts[1] if len(asset_a_parts) > 1 else None,
                )
                asset_b = Asset(
                    asset_b_parts[0],
                    asset_b_parts[1] if len(asset_a_parts) > 1 else None,
                )

                return {
                    "price": price,
                    "reserves": reserves,
                    "total_shares": float(pool["total_shares"]),
                    "LiquidityPoolAsset": LiquidityPoolAsset(
                        asset_a=asset_a, asset_b=asset_b
                    ),
                }
    except Exception as e:
        logger.warning(f"Failed to get pool data: {e}")
    return {
        "price": 1.0,
        "reserves": [{"amount": "0"}, {"amount": "0"}],
        "total_shares": 0,
        "assets": LiquidityPoolAsset(asset_a=Asset("XLM"), asset_b=Asset("XLM")),
    }


@async_cache_with_ttl(ttl_seconds=900)
async def check_asset(asset):
    try:
        response = await http_session_manager.get_web_request(
            "GET",
            f"https://horizon.stellar.org/assets?asset_code={asset.code}&asset_issuer={asset.issuer}",
            return_type="json",
        )
        if response.status == 200 and response.data["_embedded"]["records"]:
            return ""
    except Exception as e:
        logger.warning(f"Error checking asset: {e}")
    return f'<div style="color: red;">Asset {asset.code} not exist ! </div>'


async def _fetch_account(account_id):
    try:
        response = await http_session_manager.get_web_request(
            "GET",
            "https://horizon.stellar.org/accounts/" + account_id,
            return_type="json",
        )
        if response.status == 200:
            return response.data
    except Exception as e:
        logger.warning(f"Error getting account {account_id}: {e}")
    return {"balances": []}


@async_cache_with_ttl(ttl_seconds=900)
async def get_account(account_id):
    return await _fetch_account(account_id)


async def get_account_fresh(account_id):
    return await _fetch_account(account_id)


async def get_available_balance_str(account_id: str) -> str:
    """
    Loads account data, calculates the available XLM balance using the full reserve formula,
    and returns it as a formatted string.
    Returns an empty string if the account is not found or an error occurs.
    """
    account_info = await get_account(account_id)
    if not account_info or "balances" not in account_info:
        return ""

    try:
        native_balance = 0
        selling_liabilities = 0
        for balance in account_info["balances"]:
            if balance["asset_type"] == "native":
                native_balance = float(balance["balance"])
                selling_liabilities = float(balance.get("selling_liabilities", 0))
                break

        subentry_count = int(account_info.get("subentry_count", 0))
        num_sponsoring = int(account_info.get("num_sponsoring", 0))
        num_sponsored = int(account_info.get("num_sponsored", 0))

        # Full reserve formula: (2 + subentries + sponsoring - sponsored) * 0.5 XLM
        total_reserve = (2 + subentry_count + num_sponsoring - num_sponsored) * 0.5

        # Available balance: Balance - Reserve - Liabilities
        available_balance = native_balance - total_reserve - selling_liabilities

        if available_balance < 0:
            available_balance = 0

        return f"(свободно {float2str(available_balance)} XLM)"

    except (ValueError, KeyError) as e:
        logger.warning(f"Failed to calculate available balance for {account_id}: {e}")
        return ""


@async_cache_with_ttl(ttl_seconds=900)
async def get_offers(account_id):
    try:
        response = await http_session_manager.get_web_request(
            "GET",
            f"https://horizon.stellar.org/accounts/{account_id}/offers",
            return_type="json",
        )
        if response.status == 200:
            return response.data
    except Exception as e:
        logger.warning(f"Error getting offers for {account_id}: {e}")
    return {"_embedded": {"records": []}}


@async_cache_with_ttl(3600)
async def get_fund_signers():
    response = await http_session_manager.get_web_request(
        "GET",
        "https://horizon.stellar.org/accounts/" + main_fund_address,
        return_type="json",
    )
    if response.status == 200:
        data = response.data
        signers = data.get("signers", [])

        if not signers:
            return data

        # Extract all account IDs to fetch them in parallel
        account_ids = [signer["key"] for signer in signers]

        # Load all users from grist in parallel
        users_map = await load_users_from_grist(account_ids)

        # Update telegram_id for each signer
        for signer in signers:
            user = users_map.get(signer["key"])
            signer["telegram_id"] = user.telegram_id if user else 0

        return data


async def check_user_weight(need_flash=True):
    weight = 0
    if "user_id" in session:
        user_id = session["user_id"]
        logger.info(f"check_user_weight user_id {user_id}")
        fund_data = await get_fund_signers()
        if fund_data and "signers" in fund_data:
            signers = fund_data["signers"]
            for signer in signers:
                if int(signer.get("telegram_id", 0)) == int(user_id):
                    weight = signer["weight"]
                    break
            if weight == 0 and need_flash:
                await flash("User is not a signer")
        elif need_flash:
            await flash("Failed to retrieve account information")
    return weight


async def check_user_in_sign(tr_hash):
    if "user_id" in session:
        user_id = session["user_id"]

        if int(user_id) in (84131737, 3718221):
            return True

        async with current_app.db_pool() as db_session:
            repo = TransactionRepository(db_session)

            # Check if user is owner of transaction
            transaction = await repo.get_by_hash(tr_hash)
            if (
                transaction
                and transaction.owner_id
                and int(transaction.owner_id) == int(user_id)
            ):
                return True

            # Check if user is secretary for transaction account
            secretaries = await get_secretaries()
            if transaction and transaction.source_account in secretaries:
                secretary_users = secretaries[transaction.source_account]
                if any(int(user_id) == int(user) for user in secretary_users):
                    return True

            # Check if the user is a signer
            address = await repo.get_signer_by_tg_id(user_id)
            if address is None:
                return False

            # Check if the user has signed this transaction
            signature = await repo.get_signature(tr_hash, address.id)

            if signature:
                return True

    return False


async def stellar_copy_multi_sign(public_key_from, public_key_for):
    async with ServerAsync(
        horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        updated_signers = []
        call = await server.accounts().account_id(public_key_from).call()
        public_key_from_signers = call["signers"]
        updated_signers.append(
            {
                "key": "threshold",
                "high_threshold": call["thresholds"]["high_threshold"],
                "low_threshold": call["thresholds"]["low_threshold"],
                "med_threshold": call["thresholds"]["med_threshold"],
            }
        )

        public_key_for_signers = (
            await server.accounts().account_id(public_key_for).call()
        )["signers"]

    current_signers = {
        signer["key"]: signer["weight"] for signer in public_key_for_signers
    }
    new_signers = {
        signer["key"]: signer["weight"] for signer in public_key_from_signers
    }
    # переносим мастер
    new_signers[public_key_for] = new_signers[public_key_from]
    new_signers.pop(public_key_from)

    # Шаг 1: Добавляем подписантов для удаления (вес 0)
    for signer in current_signers:
        if signer not in new_signers:
            updated_signers.append({"key": signer, "weight": 0})

    # Шаг 2: Обновляем вес для существующих подписантов
    for signer, weight in current_signers.items():
        if signer in new_signers and new_signers[signer] != weight:
            updated_signers.append({"key": signer, "weight": new_signers[signer]})

    # Шаг 3: Добавляем новых подписантов
    for signer, weight in new_signers.items():
        if signer not in current_signers:
            updated_signers.append({"key": signer, "weight": weight})

    return updated_signers


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
                pool.pop("_links", None)

                # Преобразование списка reserves в словарь reserves_dict
                reserves_dict = {
                    reserve["asset"]: reserve["amount"] for reserve in pool["reserves"]
                }
                pool["reserves_dict"] = reserves_dict

                # Удаление исходного списка reserves
                pool.pop("reserves", None)

                pools.append(pool)

            page_records = await pools_call_builder.next()
        return pools


async def pay_divs(
    asset_hold: Asset,
    total_payment: float,
    payment_asset: Asset,
    require_trustline: bool = True,
):
    async with ServerAsync(
        horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        accounts = await server.accounts().for_asset(asset_hold).limit(200).call()
        holders = accounts["_embedded"]["records"]
        pools = await get_liquidity_pools_for_asset(asset_hold)

        total_assets_hold = 0
        account_assets = {}  # Словарь для хранения суммарных активов по каждому аккаунту

        # Расчет общего количества активов и активов каждого аккаунта, включая доли в пулах ликвидности
        for account in holders:
            if require_trustline and not payment_asset.is_native():
                has_trustline = any(
                    balance.get("asset_type")
                    in ["credit_alphanum4", "credit_alphanum12"]
                    and balance.get("asset_code") == payment_asset.code
                    and balance.get("asset_issuer") == payment_asset.issuer
                    for balance in account.get("balances", [])
                )
                if not has_trustline:
                    continue

            account_total_asset = 0  # Суммарное количество активов аккаунта

            for balance in account["balances"]:
                # Обработка прямых балансов актива
                if (
                    balance["asset_type"] in ["credit_alphanum4", "credit_alphanum12"]
                    and balance["asset_code"] == asset_hold.code
                    and balance["asset_issuer"] == asset_hold.issuer
                ):
                    asset_amount = float(balance["balance"])
                    account_total_asset += asset_amount
                # Обработка долей в пулах ликвидности
                elif balance["asset_type"] == "liquidity_pool_shares":
                    pool_id = balance["liquidity_pool_id"]
                    pool_share = float(balance["balance"])
                    for pool in pools:
                        if pool["id"] == pool_id:
                            asset_amount = float(
                                pool["reserves_dict"].get(
                                    f"{asset_hold.code}:{asset_hold.issuer}", 0
                                )
                            )
                            total_shares = float(pool["total_shares"])
                            if total_shares > 0 and pool_share > 0:
                                account_total_asset += (
                                    pool_share / total_shares
                                ) * asset_amount

            # Сохраняем суммарное количество активов аккаунта и обновляем общий счетчик
            account_assets[account["account_id"]] = account_total_asset
            total_assets_hold += account_total_asset

        # Расчет выплат, учитывая обновленные балансы
        payments = [
            {
                "account": account_id,
                "payment": total_payment * (amount / total_assets_hold)
                if total_assets_hold > 0
                else 0,
            }
            for account_id, amount in account_assets.items()
            if amount > 0
        ]

    return payments


async def stellar_manage_data(account_id, data_name, data_value):
    async with ServerAsync(
        horizon_url="https://horizon.stellar.org", client=AiohttpClient()
    ) as server:
        source_account = await server.load_account(account_id=account_id)
        if data_value == "":
            data_value = None

        transaction = (
            TransactionBuilder(
                source_account=source_account,
                network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
                base_fee=101010,
            )
            .append_manage_data_op(data_name=data_name, data_value=data_value)
            .set_timeout(10 * 60)
            .build()
        )
        return transaction.to_xdr()


async def add_signer(signer_key):
    username = "FaceLess"
    user_id = None

    user = await load_user_from_grist(account_id=signer_key)
    if user:
        username = user.username if user.username else "FaceLess"
        user_id = user.telegram_id

    if username != "FaceLess" and username[0] != "@":
        username = "@" + username

    async with current_app.db_pool() as db_session:
        result = await db_session.execute(
            select(Signers).filter(Signers.public_key == signer_key)
        )
        db_signer = result.scalars().first()
        if db_signer is None:
            hint = Keypair.from_public_key(signer_key).signature_hint().hex()
            db_session.add(
                Signers(
                    username=username,
                    public_key=signer_key,
                    tg_id=user_id,
                    signature_hint=hint,
                )
            )
            await db_session.commit()
        else:
            if user_id != db_signer.tg_id or username != db_signer.username:
                db_signer.tg_id = user_id
                db_signer.username = username
                await db_session.commit()


def get_operation_threshold_level(operation) -> str:
    op_name = operation.__class__.__name__

    HIGH_THRESHOLD_OPS = {"SetOptions", "AccountMerge"}

    MEDIUM_THRESHOLD_OPS = {
        "CreateAccount",
        "Payment",
        "PathPaymentStrictSend",
        "PathPaymentStrictReceive",
        "ManageBuyOffer",
        "ManageSellOffer",
        "CreatePassiveSellOffer",
        "SetOptions",
        "ChangeTrust",
        "ManageData",
        "CreateClaimableBalance",
        "BeginSponsoringFutureReserves",
        "EndSponsoringFutureReserves",
        "RevokeSponsorship",
        "Clawback",
        "ClawbackClaimableBalance",
        "LiquidityPoolDeposit",
        "LiquidityPoolWithdraw",
        "InvokeHostFunction",
        "ExtendFootprintTTL",
        "RestoreFootprint",
    }

    LOW_THRESHOLD_OPS = {
        "BumpSequence",
        "AllowTrust",
        "SetTrustLineFlags",
        "ClaimClaimableBalance",
    }

    if op_name in HIGH_THRESHOLD_OPS:
        if op_name == "SetOptions":
            if (
                operation.signer is not None
                or operation.low_threshold is not None
                or operation.med_threshold is not None
                or operation.high_threshold is not None
            ):
                return "high"
            else:
                return "med"
        else:
            return "high"

    if op_name in MEDIUM_THRESHOLD_OPS:
        return "med"

    if op_name in LOW_THRESHOLD_OPS:
        return "low"

    logger.warning(
        f"Неизвестный тип операции '{op_name}'. По умолчанию используется высокий порог."
    )
    return "high"


async def extract_sources(xdr):
    tr = TransactionEnvelope.from_xdr(
        xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
    )

    # 1. Собираем все уникальные source accounts
    unique_sources = {tr.transaction.source.account_id}
    for op in tr.transaction.operations:
        if op.source:
            unique_sources.add(op.source.account_id)

    # 2. Определяем максимальный уровень порога для каждого source
    source_max_levels = {}
    level_map = {"low": 1, "med": 2, "high": 3}
    tx_source_id = tr.transaction.source.account_id

    for source_id in unique_sources:
        max_level_for_source = "low"
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
                "GET",
                f"https://horizon.stellar.org/accounts/{source_id}",
                return_type="json",
            )
            data = response.data
            account_thresholds = data["thresholds"]
            required_threshold_value = account_thresholds[f"{max_level}_threshold"]

            signers = []
            for signer in data["signers"]:
                signers.append(
                    [
                        signer["key"],
                        signer["weight"],
                        Keypair.from_public_key(signer["key"]).signature_hint().hex(),
                    ]
                )
                await add_signer(signer["key"])

            sources_data[source_id] = {
                "threshold": required_threshold_value,
                "signers": signers,
            }

        except Exception as e:
            logger.warning(f"Failed to extract source {source_id}: {e}")
            sources_data[source_id] = {
                "threshold": 0,
                "signers": [
                    [
                        source_id,
                        1,
                        Keypair.from_public_key(source_id).signature_hint().hex(),
                    ]
                ],
            }
            await add_signer(source_id)

    return sources_data


async def update_transaction_sources(transaction: "Transactions") -> bool:
    """Обновляет поле JSON в транзакции свежими данными из Horizon."""
    try:
        # Получаем самую свежую информацию о подписантах и порогах
        fresh_sources = await extract_sources(transaction.body)

        transaction.json = json.dumps(fresh_sources)

        async with current_app.db_pool() as db_session:
            repo = TransactionRepository(db_session)
            await repo.save(transaction)
        logger.info(f"Successfully updated sources for transaction {transaction.hash}")
        return True
    except Exception as e:
        logger.error(
            f"Ошибка при обновлении источников для транзакции {transaction.hash}: {e}"
        )
        return False


async def add_transaction(tx_body, tx_description):
    try:
        tr = TransactionEnvelope.from_xdr(
            tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
        )
        tr_full = TransactionEnvelope.from_xdr(
            tx_body, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
        )
        sources = await extract_sources(tx_body)
    except Exception as ex:
        logger.info(ex)
        return False, "BAD xdr. Can`t load"

    tx_hash = tr.hash_hex()
    tr.signatures.clear()

    async with current_app.db_pool() as db_session:
        repo = TransactionRepository(db_session)
        existing_transaction = await repo.get_by_hash(tx_hash)
        if existing_transaction:
            return True, tx_hash

        owner_id = (
            int(session["userdata"]["id"])
            if "userdata" in session and "id" in session["userdata"]
            else None
        )
        new_transaction = Transactions(
            hash=tx_hash,
            body=tr.to_xdr(),
            description=tx_description,
            json=json.dumps(sources),
            stellar_sequence=tr.transaction.sequence,
            source_account=tr.transaction.source.account_id,
            owner_id=owner_id,
        )
        await repo.add(new_transaction)

        if len(tr_full.signatures) > 0:
            for signature in tr_full.signatures:
                signer = await repo.get_signer_by_signature_hint(
                    signature.signature_hint.hex()
                )
                await repo.add_signature(
                    Signatures(
                        signature_xdr=signature.to_xdr_object().to_xdr(),
                        signer_id=signer.id if signer else None,
                        transaction_hash=tx_hash,
                    )
                )
        await repo.commit()
        await db_session.commit()

    return True, tx_hash


async def create_sep7_auth_transaction(domain: str, nonce: str, callback: str) -> str:
    """Создает SEP-7 транзакцию для аутентификации с подменой адреса."""
    from stellar_sdk import Server

    server = Server("https://horizon.stellar.org")
    source_account = server.load_account(account_id=main_fund_address)

    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=100,
        )
        .append_manage_data_op(
            data_name=f"{config.domain} auth", data_value=nonce.encode()
        )
        .append_manage_data_op(
            data_name="web_auth_domain",
            data_value=domain.encode(),
            source=config.domain_account_id,
        )
        .set_timeout(300)
        .build()
    )

    transaction.transaction.sequence = 101

    r1 = stellar_uri.Replacement("sourceAccount", "X", "account to authenticate")
    replacements = [r1]

    t = stellar_uri.TransactionStellarUri(
        transaction_envelope=transaction,
        replace=replacements,
        origin_domain=config.domain,
        callback=callback,
    )

    t.sign(config.domain_key.get_secret_value())

    return t.to_uri()


async def process_xdr_transaction(signed_xdr: str) -> dict:
    """Process XDR transaction from SEP-7 callback"""
    try:
        network_passphrase = Network.PUBLIC_NETWORK_PASSPHRASE
        tx_envelope = TransactionEnvelope.from_xdr(signed_xdr, network_passphrase)
        tx = tx_envelope.transaction
        operations = tx.operations

        if len(operations) != 2:
            raise ValueError("Неверное количество операций")

        op1 = operations[0]
        expected_key = config.domain + " auth"
        if op1.data_name != expected_key:
            raise ValueError("Неверный ключ в первой операции")

        nonce_value = op1.data_value.decode() if op1.data_value is not None else ""

        op2 = operations[1]
        if (
            op2.source.account_id != config.domain_account_id
            or op2.data_name != "web_auth_domain"
        ):
            raise ValueError("Неверные данные во второй операции")

        domain_value = op2.data_value.decode() if op2.data_value is not None else ""

        return {
            "hash": tx_envelope.hash_hex(),
            "client_address": tx.source.account_id,
            "timestamp": datetime.now().isoformat(),
            "domain": domain_value,
            "nonce": nonce_value,
        }
    except Exception as e:
        raise ValueError(f"Ошибка обработки XDR: {str(e)}")


def add_trust_line_uri(public_key, asset_code, asset_issuer) -> str:
    from stellar_sdk import Server

    source_account = Server("https://horizon.stellar.org").load_account(
        account_id=public_key
    )

    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
            base_fee=101010,
        )
        .append_change_trust_op(Asset(asset_code, asset_issuer))
        .set_timeout(3600)
        .build()
    )
    r1 = stellar_uri.Replacement(
        "sourceAccount", "X", "account on which to create the trustline"
    )
    r2 = stellar_uri.Replacement("seqNum", "Y", "sequence for sourceAccount")
    replacements = [r1, r2]
    t = stellar_uri.TransactionStellarUri(
        transaction_envelope=transaction,
        replace=replacements,
        origin_domain="eurmtl.me",
    )
    t.sign(config.domain_key.get_secret_value())

    return t.to_uri()


def xdr_to_uri(xdr):
    transaction = TransactionEnvelope.from_xdr(xdr, Network.PUBLIC_NETWORK_PASSPHRASE)
    return stellar_uri.TransactionStellarUri(transaction_envelope=transaction).to_uri()


def decode_asset(asset):
    arr = asset.split("-")
    if arr[0] == "XLM":
        return Asset(arr[0])
    else:
        return Asset(arr[0], arr[1])


def decode_flags(flag_value):
    flags = TrustLineFlags(0)
    if flag_value & TrustLineFlags.AUTHORIZED_FLAG:
        flags |= TrustLineFlags.AUTHORIZED_FLAG
    if flag_value & TrustLineFlags.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG:
        flags |= TrustLineFlags.AUTHORIZED_TO_MAINTAIN_LIABILITIES_FLAG
    if flag_value & TrustLineFlags.TRUSTLINE_CLAWBACK_ENABLED_FLAG:
        flags |= TrustLineFlags.TRUSTLINE_CLAWBACK_ENABLED_FLAG
    return flags


async def stellar_build_xdr(data):
    from stellar_sdk import Server

    root_account = Server(horizon_url="https://horizon.stellar.org").load_account(
        data["publicKey"]
    )
    if "sequence" in data and int(data["sequence"]) > 0:
        root_account.sequence = int(data["sequence"]) - 1

    transaction = TransactionBuilder(
        source_account=root_account,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        base_fee=10101,
    )
    transaction.set_timeout(60 * 60 * 24 * 7)

    def build_claim_predicate(predicate_type: str, predicate_value: str) -> ClaimPredicate:
        if predicate_type == "unconditional":
            return ClaimPredicate.predicate_unconditional()

        if not predicate_value:
            raise ValueError("Predicate value is required for claimable balance.")

        if predicate_type in ("abs_before", "abs_after"):
            dt_value = datetime.fromisoformat(predicate_value.replace("Z", "+00:00"))
            abs_before = int(dt_value.timestamp())
            predicate = ClaimPredicate.predicate_before_absolute_time(abs_before)
            return ClaimPredicate.predicate_not(predicate) if predicate_type == "abs_after" else predicate

        if predicate_type in ("rel_before", "rel_after"):
            rel_before = int(predicate_value)
            predicate = ClaimPredicate.predicate_before_relative_time(rel_before)
            return ClaimPredicate.predicate_not(predicate) if predicate_type == "rel_after" else predicate

        raise ValueError(f"Unknown claim predicate type: {predicate_type}")
    if data["memo_type"] == "memo_text":
        transaction.add_text_memo(data["memo"])
    if data["memo_type"] == "memo_hash":
        transaction.add_hash_memo(data["memo"])
    for operation in data["operations"]:
        source_account_raw = operation.get("sourceAccount") or ""
        source_account = (
            source_account_raw
            if isinstance(source_account_raw, str) and len(source_account_raw) == 56
            else None
        )
        if operation["type"] == "payment":
            transaction.append_payment_op(
                destination=operation["destination"],
                asset=decode_asset(operation["asset"]),
                amount=float2str(operation["amount"]),
                source=source_account,
            )
        if operation["type"] == "clawback":
            transaction.append_clawback_op(
                from_=operation["from"],
                asset=decode_asset(operation["asset"]),
                amount=float2str(operation["amount"]),
                source=source_account,
            )
        if operation["type"] == "claim_claimable_balance":
            balance_id = operation["balanceId"]
            if len(balance_id) == 64:
                balance_id = balance_id.rjust(72, "0")
            transaction.append_claim_claimable_balance_op(
                balance_id=balance_id, source=source_account
            )
        if operation["type"] == "copy_multi_sign":
            public_key = source_account if source_account else data["publicKey"]
            updated_signers = await stellar_copy_multi_sign(
                public_key_from=operation["from"], public_key_for=public_key
            )
            for signer in updated_signers:
                if signer["key"] == public_key:
                    transaction.append_set_options_op(
                        master_weight=signer["weight"], source=source_account
                    )
                elif signer["key"] == "threshold":
                    transaction.append_set_options_op(
                        med_threshold=signer["med_threshold"],
                        low_threshold=signer["low_threshold"],
                        high_threshold=signer["high_threshold"],
                        source=source_account,
                    )
                else:
                    transaction.append_ed25519_public_key_signer(
                        account_id=signer["key"],
                        weight=signer["weight"],
                        source=source_account,
                    )
        if operation["type"] == "trust_payment":
            transaction.append_set_trust_line_flags_op(
                trustor=operation["destination"],
                asset=decode_asset(operation["asset"]),
                set_flags=TrustLineFlags.AUTHORIZED_FLAG,
                source=source_account,
            )
            transaction.append_payment_op(
                destination=operation["destination"],
                asset=decode_asset(operation["asset"]),
                amount=float2str(operation["amount"]),
                source=source_account,
            )
            transaction.append_set_trust_line_flags_op(
                trustor=operation["destination"],
                asset=decode_asset(operation["asset"]),
                clear_flags=TrustLineFlags.AUTHORIZED_FLAG,
                source=source_account,
            )
        if operation["type"] == "change_trust":
            transaction.append_change_trust_op(
                asset=decode_asset(operation["asset"]),
                limit=operation["limit"] if len(operation["limit"]) > 0 else None,
                source=source_account,
            )
        if operation["type"] == "create_account":
            transaction.append_create_account_op(
                destination=operation["destination"],
                starting_balance=operation["startingBalance"],
                source=source_account,
            )
        if operation["type"] == "create_claimable_balance":
            claimants = []
            for claimant_index in (1, 2):
                destination = operation.get(
                    f"claimant_{claimant_index}_destination", ""
                ).strip()
                if not destination:
                    continue
                predicate_type = operation.get(
                    f"claimant_{claimant_index}_predicate_type", "unconditional"
                )
                predicate_value = operation.get(
                    f"claimant_{claimant_index}_predicate_value", ""
                )
                predicate = build_claim_predicate(
                    predicate_type, predicate_value.strip()
                )
                claimants.append(Claimant(destination=destination, predicate=predicate))

            if not claimants:
                raise ValueError("At least one claimant is required.")

            transaction.append_create_claimable_balance_op(
                asset=decode_asset(operation["asset"]),
                amount=float2str(operation["amount"]),
                claimants=claimants,
                source=source_account,
            )
        if operation["type"] == "sell":
            transaction.append_manage_sell_offer_op(
                selling=decode_asset(operation["selling"]),
                buying=decode_asset(operation["buying"]),
                amount=float2str(operation["amount"]),
                price=float2str(operation["price"]),
                offer_id=int(operation["offer_id"]),
                source=source_account,
            )
        if operation["type"] == "swap":
            asset_path = []
            for asset in json.loads(operation["path"]):
                if asset["asset_type"] == "native":
                    asset_path.append(decode_asset(f"XLM"))
                else:
                    asset_path.append(
                        decode_asset(f"{asset['asset_code']}-{asset['asset_issuer']}")
                    )
            transaction.append_path_payment_strict_send_op(
                path=asset_path,
                destination=source_account if source_account else data["publicKey"],
                send_asset=decode_asset(operation["selling"]),
                dest_asset=decode_asset(operation["buying"]),
                send_amount=float2str(operation["amount"]),
                dest_min=float2str(operation["destination"]),
                source=source_account,
            )
        if operation["type"] == "sell_passive":
            transaction.append_create_passive_sell_offer_op(
                selling=decode_asset(operation["selling"]),
                buying=decode_asset(operation["buying"]),
                amount=float2str(operation["amount"]),
                price=float2str(operation["price"]),
                source=source_account,
            )
        if operation["type"] == "buy":
            transaction.append_manage_buy_offer_op(
                selling=decode_asset(operation["selling"]),
                buying=decode_asset(operation["buying"]),
                amount=float2str(operation["amount"]),
                price=float2str(operation["price"]),
                offer_id=int(operation["offer_id"]),
                source=source_account,
            )
        if operation["type"] == "manage_data":
            transaction.append_manage_data_op(
                data_name=operation["data_name"],
                data_value=operation["data_value"]
                if len(operation["data_value"]) > 0
                else None,
                source=source_account,
            )
        if operation["type"] == "set_options":
            threshold = operation["threshold"]
            if threshold and "/" in str(threshold):
                low, med, high = map(int, threshold.split("/"))
            else:
                low = med = high = int(threshold) if threshold else None

            transaction.append_set_options_op(
                master_weight=int(operation["master"])
                if operation.get("master")
                else None,
                med_threshold=med,
                high_threshold=high,
                low_threshold=low,
                home_domain=operation["home"] if operation.get("home") else None,
                source=source_account,
            )
        if operation["type"] == "set_options_signer":
            transaction.append_ed25519_public_key_signer(
                account_id=operation["signerAccount"]
                if len(operation["signerAccount"]) > 55
                else None,
                weight=int(operation["weight"])
                if len(operation["weight"]) > 0
                else None,
                source=source_account,
            )
        if operation["type"] == "set_trust_line_flags":
            set_flags_decoded = (
                decode_flags(int(operation["setFlags"]))
                if len(operation["setFlags"]) > 0
                else None
            )
            clear_flags_decoded = (
                decode_flags(int(operation["clearFlags"]))
                if len(operation["clearFlags"]) > 0
                else None
            )

            transaction.append_set_trust_line_flags_op(
                trustor=operation["trustor"],
                asset=decode_asset(operation["asset"]),
                set_flags=set_flags_decoded,
                clear_flags=clear_flags_decoded,
                source=source_account,
            )
        if operation["type"] == "bump_sequence":
            transaction.append_bump_sequence_op(
                bump_to=int(operation["bump_to"]), source=source_account
            )
        if operation["type"] == "begin_sponsoring_future_reserves":
            transaction.append_begin_sponsoring_future_reserves_op(
                sponsored_id=operation["sponsored_id"], source=source_account
            )
        if operation["type"] == "end_sponsoring_future_reserves":
            transaction.append_end_sponsoring_future_reserves_op(source=source_account)
        if operation["type"] == "revoke_sponsorship":
            revoke_type = operation.get("revoke_type")
            if revoke_type == "account":
                transaction.append_revoke_account_sponsorship_op(
                    account_id=operation["revoke_account_id"], source=source_account
                )
            elif revoke_type == "trustline":
                transaction.append_revoke_trustline_sponsorship_op(
                    account_id=operation["revoke_trustline_account"],
                    asset=decode_asset(operation["revoke_trustline_asset"]),
                    source=source_account,
                )
            elif revoke_type == "data":
                transaction.append_revoke_data_sponsorship_op(
                    account_id=operation["revoke_data_account"],
                    data_name=operation["revoke_data_name"],
                    source=source_account,
                )
            elif revoke_type == "offer":
                transaction.append_revoke_offer_sponsorship_op(
                    seller_id=operation["revoke_offer_seller"],
                    offer_id=int(operation["revoke_offer_id"]),
                    source=source_account,
                )
            elif revoke_type == "claimable_balance":
                balance_id = operation["revoke_claimable_balance_id"]
                if len(balance_id) == 64:
                    balance_id = balance_id.rjust(72, "0")
                transaction.append_revoke_claimable_balance_sponsorship_op(
                    claimable_balance_id=balance_id, source=source_account
                )
            elif revoke_type == "liquidity_pool":
                transaction.append_revoke_liquidity_pool_sponsorship_op(
                    liquidity_pool_id=operation["revoke_liquidity_pool_id"],
                    source=source_account,
                )
            elif revoke_type == "signer":
                transaction.append_revoke_ed25519_public_key_signer_sponsorship_op(
                    account_id=operation["revoke_signer_account"],
                    signer_key=operation["revoke_signer_key"],
                    source=source_account,
                )
        if operation["type"] == "pay_divs":
            require_trustline = True
            raw_flag = (
                operation.get("require_trustline")
                if "require_trustline" in operation
                else operation.get("requireTrustline")
            )
            if raw_flag is not None:
                try:
                    require_trustline = bool(int(raw_flag))
                except (TypeError, ValueError):
                    require_trustline = True

            payout_asset = decode_asset(operation["asset"])
            for record in await pay_divs(
                decode_asset(operation["holders"]),
                float(operation["amount"]),
                payout_asset,
                require_trustline=require_trustline,
            ):
                if round(record["payment"], 7) > 0:
                    transaction.append_payment_op(
                        destination=record["account"],
                        asset=payout_asset,
                        amount=float2str(record["payment"]),
                        source=source_account,
                    )

        if operation["type"] == "liquidity_pool_deposit":
            min_price = float(operation["min_price"])
            max_price = float(operation["max_price"])

            if min_price == 0 or max_price == 0:
                pool_data = await get_pool_data(operation["liquidity_pool_id"])
                current_price = pool_data["price"]
                if min_price == 0:
                    min_price = current_price * 0.95
                if max_price == 0:
                    max_price = current_price * 1.05

            transaction.append_liquidity_pool_deposit_op(
                liquidity_pool_id=operation["liquidity_pool_id"],
                max_amount_a=float2str(operation["max_amount_a"]),
                max_amount_b=float2str(operation["max_amount_b"]),
                min_price=float2str(min_price),
                max_price=float2str(max_price),
                source=source_account,
            )
        if operation["type"] == "liquidity_pool_withdraw":
            min_amount_a = float(operation["min_amount_a"])
            min_amount_b = float(operation["min_amount_b"])

            if min_amount_a == 0 or min_amount_b == 0:
                pool_data = await get_pool_data(operation["liquidity_pool_id"])
                share_ratio = float(operation["amount"]) / pool_data["total_shares"]

                if min_amount_a == 0:
                    min_amount_a = pool_data["reserves"][0]["amount"]
                    min_amount_a = float(min_amount_a) * share_ratio * 0.95
                if min_amount_b == 0:
                    min_amount_b = pool_data["reserves"][1]["amount"]
                    min_amount_b = float(min_amount_b) * share_ratio * 0.95

            transaction.append_liquidity_pool_withdraw_op(
                liquidity_pool_id=operation["liquidity_pool_id"],
                amount=float2str(operation["amount"]),
                min_amount_a=float2str(min_amount_a),
                min_amount_b=float2str(min_amount_b),
                source=source_account,
            )
        if operation["type"] == "liquidity_pool_trustline":
            pool_data = await get_pool_data(operation["liquidity_pool_id"])
            transaction.append_change_trust_op(
                asset=pool_data["LiquidityPoolAsset"],
                source=source_account,
                limit=operation["limit"] if len(operation["limit"]) > 0 else None,
            )
    transaction = transaction.build()
    xdr = transaction.to_xdr()
    return xdr
