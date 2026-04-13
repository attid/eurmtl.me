from __future__ import annotations

import asyncio
import base64

import aiohttp
from loguru import logger
from stellar_sdk import (
    Account,
    Network,
    SorobanServer,
    TransactionBuilder,
    TransactionEnvelope,
    scval,
    xdr as stellar_xdr,
)
from stellar_sdk.sep import stellar_uri

PREPARED_TRANSACTION_TIMEOUT_SECONDS = 300
SUBMIT_TRANSACTION_POLL_ATTEMPTS = 10
SUBMIT_TRANSACTION_POLL_INTERVAL_SECONDS = 1


def _decode_send_transaction_error(send_response) -> str:
    error_result_xdr = getattr(send_response, "error_result_xdr", None)
    if not error_result_xdr:
        return "Sending transaction failed"
    try:
        result = stellar_xdr.TransactionResult.from_xdr(error_result_xdr)
        code_value = result.result.code
        code_name = stellar_xdr.TransactionResultCode(code_value).name
        return f"Sending transaction failed: {code_name}"
    except Exception:
        return "Sending transaction failed"


async def _post_json_rpc(url: str, payload: dict) -> dict:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            data = await response.json()
            return {"status": response.status, "data": data}


async def read_contract_value(
    contract_id: str,
    function_name: str,
    params: list | None = None,
    rpc_url: str = "https://soroban-rpc.mainnet.stellar.gateway.fm",
) -> dict:
    params = params or []
    transaction = (
        TransactionBuilder(
            source_account=Account(
                "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF",
                sequence=0,
            ),
            base_fee=200,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        )
        .append_invoke_contract_function_op(
            contract_id=contract_id,
            function_name=function_name,
            parameters=params,
        )
        .set_timeout(0)
        .build()
    )
    response = await _post_json_rpc(
        rpc_url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "simulateTransaction",
            "params": {
                "xdrFormat": "json",
                "transaction": transaction.to_xdr(),
                "authMode": "",
            },
        },
    )
    if response["status"] != 200:
        raise ValueError(str(response["data"]))

    results = response["data"].get("result", {}).get("results", [])
    if not results:
        raise ValueError("simulateTransaction returned no results")

    first_result = results[0]
    if "returnValueJson" in first_result:
        return first_result["returnValueJson"]
    if "xdr" in first_result:
        return {"xdr": first_result["xdr"]}
    raise ValueError("simulateTransaction returned unsupported result format")


async def read_contract_string(
    rpc_url: str, contract_id: str, function_name: str
) -> str:
    try:
        return_value = await read_contract_value(
            contract_id=contract_id,
            function_name=function_name,
            rpc_url=rpc_url,
        )
        if "string" in return_value:
            return return_value["string"]

        xdr_value = return_value.get("xdr")
        if xdr_value:
            decoded = base64.b64decode(xdr_value)
            if len(decoded) >= 8:
                string_length = int.from_bytes(decoded[4:8], byteorder="big")
                string_bytes = decoded[8 : 8 + string_length]
                return string_bytes.decode("utf-8")

        raise ValueError("simulateTransaction returned unsupported result format")
    except Exception as exc:
        raise ValueError(str(exc)) from exc


async def prepare_contract_transaction_uri(
    rpc_url: str,
    contract_id: str,
    function_name: str,
    source_account_id: str,
    parameters: list,
    callback_url: str,
    message: str,
    origin_domain: str,
    signer_secret: str,
    token_contract_id: str | None = None,
    approve_expiration_ledger_offset: int = 1000,
) -> dict:
    server = SorobanServer(rpc_url)
    source_account = server.load_account(source_account_id)
    builder = TransactionBuilder(
        source_account=source_account,
        base_fee=10_000,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
    )
    if token_contract_id:
        latest_ledger_response = server.get_latest_ledger()
        latest_ledger = int(latest_ledger_response.sequence)
        approve_expiration_ledger = latest_ledger + approve_expiration_ledger_offset
        approve_parameters = [
            scval.to_address(source_account_id),
            scval.to_address(contract_id),
            parameters[1],
            scval.to_uint32(approve_expiration_ledger),
        ]
        builder.append_invoke_contract_function_op(
            contract_id=token_contract_id,
            function_name="approve",
            parameters=approve_parameters,
        )
    builder.append_invoke_contract_function_op(
        contract_id=contract_id,
        function_name=function_name,
        parameters=parameters,
    )
    transaction = builder.set_timeout(PREPARED_TRANSACTION_TIMEOUT_SECONDS).build()
    logger.info(
        "Preparing Soroban contract transaction: contract_id={} token_contract_id={} function={} source={} callback={} tx_xdr={} ",
        contract_id,
        token_contract_id,
        function_name,
        source_account_id,
        callback_url,
        transaction.to_xdr(),
    )
    try:
        try:
            simulate_response = await _post_json_rpc(
                rpc_url,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "simulateTransaction",
                    "params": {
                        "xdrFormat": "json",
                        "transaction": transaction.to_xdr(),
                        "authMode": "",
                    },
                },
            )
            logger.info(
                "Soroban simulateTransaction response before prepare: contract_id={} token_contract_id={} function={} source={} response={}",
                contract_id,
                token_contract_id,
                function_name,
                source_account_id,
                simulate_response,
            )
        except Exception as simulate_exc:
            logger.exception(
                "Soroban simulateTransaction preflight failed: contract_id={} token_contract_id={} function={} source={} error={}",
                contract_id,
                token_contract_id,
                function_name,
                source_account_id,
                str(simulate_exc),
            )
        prepared_transaction = server.prepare_transaction(transaction)
    except Exception as exc:
        logger.exception(
            "Soroban prepare_transaction failed: contract_id={} token_contract_id={} function={} source={} params_count={} callback={} error={}",
            contract_id,
            token_contract_id,
            function_name,
            source_account_id,
            len(parameters),
            callback_url,
            str(exc),
        )
        raise
    transaction_uri = stellar_uri.TransactionStellarUri(
        transaction_envelope=prepared_transaction,
        callback=callback_url,
        origin_domain=origin_domain,
        message=message,
    )
    transaction_uri.sign(signer_secret)
    return {
        "uri": transaction_uri.to_uri(),
        "xdr": prepared_transaction.to_xdr(),
    }


async def submit_signed_transaction(rpc_url: str, signed_xdr: str) -> dict:
    try:
        server = SorobanServer(rpc_url)
        transaction = TransactionEnvelope.from_xdr(
            signed_xdr,
            Network.PUBLIC_NETWORK_PASSPHRASE,
        )
        send_response = server.send_transaction(transaction)
        tx_hash = getattr(send_response, "hash", "") or ""
        if getattr(send_response, "status", None) != "PENDING":
            return {
                "ok": False,
                "tx_hash": tx_hash,
                "error": _decode_send_transaction_error(send_response),
            }

        for attempt in range(SUBMIT_TRANSACTION_POLL_ATTEMPTS):
            get_response = server.get_transaction(tx_hash)
            status = getattr(get_response, "status", None)
            if status == "SUCCESS":
                return {"ok": True, "tx_hash": tx_hash, "error": ""}
            if status in {"FAILED", "ERROR"}:
                return {"ok": False, "tx_hash": tx_hash, "error": "Transaction failed"}
            if attempt < SUBMIT_TRANSACTION_POLL_ATTEMPTS - 1:
                await asyncio.sleep(SUBMIT_TRANSACTION_POLL_INTERVAL_SECONDS)

        return {
            "ok": True,
            "tx_hash": tx_hash,
            "error": "",
        }
    except Exception as exc:
        return {"ok": False, "tx_hash": "", "error": str(exc)}
