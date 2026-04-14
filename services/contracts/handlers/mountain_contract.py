from __future__ import annotations

from decimal import Decimal

from stellar_sdk import StrKey, scval

from other.config_reader import config
from other.stellar_soroban import (
    prepare_contract_transaction_uri,
    read_contract_string,
    read_contract_value,
)

MOUNTAIN_CONTRACT_ID = "CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM"
MOUNTAIN_TOKEN_CONTRACT_ID = "CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK"
HIDDEN_CONTRACT_ID = "CBHIDDENCONTRACTXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
EURMTL_RAW_SCALE = Decimal("10000000")


def choose_candidate_address(
    detected_address: str | None,
    session_address: str | None,
) -> str:
    if detected_address:
        return detected_address
    if session_address:
        return session_address
    return ""


def _normalize_i128_like(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        for key in ("i128", "u128", "i64", "u64", "i32", "u32"):
            inner = value.get(key)
            if inner is not None:
                return _normalize_i128_like(inner)
    raise ValueError("simulateTransaction returned unsupported range format")


def _extract_range_pair(payload: dict) -> tuple[str, str]:
    if "vec" in payload and isinstance(payload["vec"], list) and len(payload["vec"]) == 2:
        return (
            _normalize_i128_like(payload["vec"][0]),
            _normalize_i128_like(payload["vec"][1]),
        )
    if "tuple" in payload and isinstance(payload["tuple"], list) and len(payload["tuple"]) == 2:
        return (
            _normalize_i128_like(payload["tuple"][0]),
            _normalize_i128_like(payload["tuple"][1]),
        )
    raise ValueError("simulateTransaction returned unsupported range format")


def format_raw_amount_to_eurmtl(raw_amount: str) -> str:
    amount = Decimal(raw_amount) / EURMTL_RAW_SCALE
    normalized = format(amount.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def validate_capture_form(
    user: str,
    amount: str,
    msg: str,
    min_amount_raw: str = "",
    max_amount_raw: str = "",
) -> str:
    if not user or not amount or not msg:
        return "user, amount and msg are required"
    if amount == "0":
        return "user, amount and msg are required"
    if not StrKey.is_valid_ed25519_public_key(user):
        return "user must be a valid Stellar address"
    try:
        parsed_amount = int(amount)
    except ValueError:
        return "amount must be an integer"
    if min_amount_raw and max_amount_raw:
        min_amount = int(min_amount_raw)
        max_amount = int(max_amount_raw)
        if parsed_amount < min_amount or parsed_amount > max_amount:
            return f"amount must be between {min_amount_raw} and {max_amount_raw} raw units"
    return ""


async def prepare_capture_flow(
    contract_id: str,
    user: str,
    amount: str,
    msg: str,
    callback_url: str,
) -> dict:
    parameters = [
        scval.to_address(user),
        scval.to_int128(int(amount)),
        scval.to_string(msg),
    ]
    return await prepare_contract_transaction_uri(
        rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
        contract_id=contract_id,
        function_name="capture",
        source_account_id=user,
        parameters=parameters,
        callback_url=callback_url,
        message="Capture the mountain",
        origin_domain=config.domain,
        signer_secret=config.domain_key.get_secret_value(),
        token_contract_id=None,
        approve_expiration_ledger_offset=None,
    )


async def load_message(contract_id: str) -> dict:
    try:
        message = await read_contract_string(
            rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
            contract_id=contract_id,
            function_name="message",
        )
        return {"ok": True, "message": message, "error": ""}
    except ValueError as exc:
        return {"ok": False, "message": "", "error": str(exc)}


async def load_range(contract_id: str) -> dict:
    try:
        range_value = await read_contract_value(
            contract_id=contract_id,
            function_name="get_range",
            rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
        )
        min_amount_raw, max_amount_raw = _extract_range_pair(range_value)
        return {
            "ok": True,
            "min_amount_raw": min_amount_raw,
            "max_amount_raw": max_amount_raw,
            "min_amount_eurmtl": format_raw_amount_to_eurmtl(min_amount_raw),
            "max_amount_eurmtl": format_raw_amount_to_eurmtl(max_amount_raw),
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "min_amount_raw": "",
            "max_amount_raw": "",
            "min_amount_eurmtl": "",
            "max_amount_eurmtl": "",
            "error": str(exc),
        }


def build_mountain_contract_definition() -> dict:
    return {
        "contract_id": MOUNTAIN_CONTRACT_ID,
        "title": "King of the Mountain",
        "description": "Human-friendly interface for the mountain contract.",
        "public": True,
        "blocks": [
            {
                "name": "message",
                "title": "Current message",
                "description": "Shows the current king message from the contract",
            },
            {
                "name": "capture",
                "title": "Capture the mountain",
                "description": "Creates a capture(user, amount, msg) contract call",
                "fields": [
                    {"name": "user", "label": "User address", "type": "address"},
                    {"name": "amount", "label": "Amount", "type": "i128"},
                    {"name": "msg", "label": "Message", "type": "string"},
                ],
            },
        ],
    }


def build_hidden_contract_definition() -> dict:
    return {
        "contract_id": HIDDEN_CONTRACT_ID,
        "title": "Hidden test contract",
        "description": "Internal-only contract screen for direct-link testing.",
        "public": False,
        "blocks": [],
    }
