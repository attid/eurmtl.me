from __future__ import annotations

from stellar_sdk import StrKey, scval

from other.config_reader import config
from other.stellar_soroban import prepare_contract_transaction_uri, read_contract_string

MOUNTAIN_CONTRACT_ID = "CAFXUALXFPTBTLSRCDSMJXNPSN3AVL2ZPXJUDDHVTUTLRX5SCNP2SISM"
MOUNTAIN_TOKEN_CONTRACT_ID = "CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK"
HIDDEN_CONTRACT_ID = "CBHIDDENCONTRACTXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"


def choose_candidate_address(
    detected_address: str | None,
    session_address: str | None,
) -> str:
    if detected_address:
        return detected_address
    if session_address:
        return session_address
    return ""


def validate_capture_form(user: str, amount: str, msg: str) -> str:
    if not user or not amount or not msg:
        return "user, amount and msg are required"
    if amount == "0":
        return "user, amount and msg are required"
    if not StrKey.is_valid_ed25519_public_key(user):
        return "user must be a valid Stellar address"
    try:
        int(amount)
    except ValueError:
        return "amount must be an integer"
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
        token_contract_id=MOUNTAIN_TOKEN_CONTRACT_ID,
        approve_expiration_ledger_offset=1000,
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
