from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_UP

from stellar_sdk import StrKey, scval

from other.config_reader import config
from other.stellar_soroban import prepare_contract_transaction_uri, read_contract_value
from services.stellar_client import float2str

SWAP_POOL_CONTRACT_ID = "CCEBV2EC6Z6TE2632XXTEBD6KA2U57LRIEDGV2SU77BOF2HKKB4HDIM2"
TOKEN_LABELS_BY_ADDRESS = {
    "CDKLJRIL7E2OWHTPTIHCAXTXI6PEXFOS6PJFAFCDBYWDT3B3QI42EOJA": "USDM",
    "CDUYP3U6HGTOBUNQD2WTLWNMNADWMENROKZZIHGEVGKIU3ZUDF42CDOK": "EURMTL",
}
TOKEN_INDEX_BY_LABEL = {"USDM": 0, "EURMTL": 1}
TOKEN_DECIMALS = 7
ALLOWED_SLIPPAGE_PERCENTAGES = {"1", "3", "5"}
DEFAULT_SLIPPAGE_PERCENT = "1"


def human_to_token_amount(value: str, decimals: int = TOKEN_DECIMALS) -> int:
    amount = Decimal(float2str(value))
    scale = Decimal(10) ** decimals
    return int((amount * scale).quantize(Decimal("1"), rounding=ROUND_DOWN))


def format_token_amount(value: int | str, decimals: int = TOKEN_DECIMALS) -> str:
    amount = Decimal(str(value)) / (Decimal(10) ** decimals)
    normalized = format(amount.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def normalize_swap_direction(from_token: str, to_token: str) -> tuple[int, int]:
    return TOKEN_INDEX_BY_LABEL[from_token], TOKEN_INDEX_BY_LABEL[to_token]


async def load_pool_overview() -> dict:
    contract_name = await read_contract_value(SWAP_POOL_CONTRACT_ID, "contract_name")
    pool_type = await read_contract_value(SWAP_POOL_CONTRACT_ID, "pool_type")
    tokens = await read_contract_value(SWAP_POOL_CONTRACT_ID, "get_tokens")
    reserves = await read_contract_value(SWAP_POOL_CONTRACT_ID, "get_reserves")
    fee_fraction = await read_contract_value(SWAP_POOL_CONTRACT_ID, "get_fee_fraction")

    token_addresses = [item["address"] for item in tokens["vec"]]
    token_labels = [TOKEN_LABELS_BY_ADDRESS[address] for address in token_addresses]
    reserve_values = [format_token_amount(item["u128"]) for item in reserves["vec"]]

    return {
        "contract_name": contract_name["symbol"],
        "pool_type": pool_type["symbol"],
        "tokens": token_labels,
        "reserves": reserve_values,
        "fee_fraction": fee_fraction["u32"],
    }


async def estimate_swap_exact_in(
    from_token: str, to_token: str, amount_in: str
) -> dict:
    in_idx, out_idx = normalize_swap_direction(from_token, to_token)
    raw_amount_in = human_to_token_amount(amount_in)
    result = await read_contract_value(
        contract_id=SWAP_POOL_CONTRACT_ID,
        function_name="estimate_swap",
        params=[
            scval.to_uint32(in_idx),
            scval.to_uint32(out_idx),
            scval.to_uint128(raw_amount_in),
        ],
    )
    return {
        "ok": True,
        "amount_in": amount_in,
        "estimated_out": format_token_amount(result["u128"]),
        "from_token": from_token,
        "to_token": to_token,
    }


async def estimate_swap_exact_out(
    from_token: str, to_token: str, amount_out: str
) -> dict:
    in_idx, out_idx = normalize_swap_direction(from_token, to_token)
    raw_amount_out = human_to_token_amount(amount_out)
    result = await read_contract_value(
        contract_id=SWAP_POOL_CONTRACT_ID,
        function_name="estimate_swap_strict_receive",
        params=[
            scval.to_uint32(in_idx),
            scval.to_uint32(out_idx),
            scval.to_uint128(raw_amount_out),
        ],
    )
    return {
        "ok": True,
        "amount_out": amount_out,
        "estimated_in": format_token_amount(result["u128"]),
        "from_token": from_token,
        "to_token": to_token,
    }


def apply_exact_in_slippage(quoted_amount_out: str, slippage_percent: str) -> str:
    quoted = Decimal(quoted_amount_out)
    factor = Decimal("1") - (Decimal(slippage_percent) / Decimal("100"))
    protected = quoted * factor
    return format_token_amount(human_to_token_amount(str(protected)))


def apply_exact_out_slippage(quoted_amount_in: str, slippage_percent: str) -> str:
    quoted = Decimal(quoted_amount_in)
    factor = Decimal("1") + (Decimal(slippage_percent) / Decimal("100"))
    protected = (quoted * factor).quantize(
        Decimal("1") / (Decimal(10) ** TOKEN_DECIMALS), rounding=ROUND_UP
    )
    return format_token_amount(human_to_token_amount(str(protected)))


def _validate_swap_form(user: str, amount: str, slippage_percent: str) -> str:
    if not user or not amount:
        return "user and amount are required"
    if not StrKey.is_valid_ed25519_public_key(user):
        return "user must be a valid Stellar address"
    try:
        parsed_amount = Decimal(float2str(amount))
    except Exception:
        return "amount must be a decimal number"
    if parsed_amount <= 0:
        return "amount must be greater than 0"
    if slippage_percent not in ALLOWED_SLIPPAGE_PERCENTAGES:
        return "slippage must be one of 1, 3, or 5"
    return ""


def validate_swap_exact_in_form(
    user: str, amount_in: str, slippage_percent: str = DEFAULT_SLIPPAGE_PERCENT
) -> str:
    return _validate_swap_form(user, amount_in, slippage_percent)


def validate_swap_exact_out_form(
    user: str, amount_out: str, slippage_percent: str = DEFAULT_SLIPPAGE_PERCENT
) -> str:
    return _validate_swap_form(user, amount_out, slippage_percent)


async def prepare_swap_exact_in_flow(
    user: str,
    from_token: str,
    to_token: str,
    amount_in: str,
    callback_url: str,
    slippage_percent: str = DEFAULT_SLIPPAGE_PERCENT,
) -> dict:
    in_idx, out_idx = normalize_swap_direction(from_token, to_token)
    raw_amount_in = human_to_token_amount(amount_in)
    quote = await estimate_swap_exact_in(from_token, to_token, amount_in)
    min_amount_out = human_to_token_amount(
        apply_exact_in_slippage(quote["estimated_out"], slippage_percent)
    )
    return await prepare_contract_transaction_uri(
        rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
        contract_id=SWAP_POOL_CONTRACT_ID,
        function_name="swap",
        source_account_id=user,
        parameters=[
            scval.to_address(user),
            scval.to_uint32(in_idx),
            scval.to_uint32(out_idx),
            scval.to_uint128(raw_amount_in),
            scval.to_uint128(min_amount_out),
        ],
        callback_url=callback_url,
        message=f"Swap {amount_in} {from_token} to {to_token}",
        origin_domain=config.domain,
        signer_secret=config.domain_key.get_secret_value(),
    )


async def prepare_swap_exact_out_flow(
    user: str,
    from_token: str,
    to_token: str,
    amount_out: str,
    callback_url: str,
    slippage_percent: str = DEFAULT_SLIPPAGE_PERCENT,
) -> dict:
    in_idx, out_idx = normalize_swap_direction(from_token, to_token)
    raw_amount_out = human_to_token_amount(amount_out)
    quote = await estimate_swap_exact_out(from_token, to_token, amount_out)
    max_amount_in = human_to_token_amount(
        apply_exact_out_slippage(quote["estimated_in"], slippage_percent)
    )
    return await prepare_contract_transaction_uri(
        rpc_url="https://soroban-rpc.mainnet.stellar.gateway.fm",
        contract_id=SWAP_POOL_CONTRACT_ID,
        function_name="swap_strict_receive",
        source_account_id=user,
        parameters=[
            scval.to_address(user),
            scval.to_uint32(in_idx),
            scval.to_uint32(out_idx),
            scval.to_uint128(raw_amount_out),
            scval.to_uint128(max_amount_in),
        ],
        callback_url=callback_url,
        message=f"Swap to receive {amount_out} {to_token}",
        origin_domain=config.domain,
        signer_secret=config.domain_key.get_secret_value(),
    )


def build_swap_pool_contract_definition() -> dict:
    return {
        "contract_id": SWAP_POOL_CONTRACT_ID,
        "title": "USDM / EURMTL Swap",
        "description": "Human-friendly swap interface for the USDM/EURMTL pool.",
        "public": True,
        "blocks": [
            {
                "name": "pool_overview",
                "title": "Pool overview",
                "description": "Current pool type, tokens, reserves, and fee.",
            },
            {
                "name": "exact_in",
                "title": "Exact in",
                "description": "Estimate output and swap a fixed input amount.",
            },
            {
                "name": "exact_out",
                "title": "Exact out",
                "description": "Estimate required input and swap for a fixed output amount.",
            },
        ],
    }
