from __future__ import annotations

from services.contracts.handlers.mountain_contract import (
    HIDDEN_CONTRACT_ID,
    MOUNTAIN_CONTRACT_ID,
    build_hidden_contract_definition,
    build_mountain_contract_definition,
)
from services.contracts.handlers.swap_pool_contract import (
    SWAP_POOL_CONTRACT_ID,
    build_swap_pool_contract_definition,
)

_CONTRACTS = {
    MOUNTAIN_CONTRACT_ID: build_mountain_contract_definition(),
    SWAP_POOL_CONTRACT_ID: build_swap_pool_contract_definition(),
    HIDDEN_CONTRACT_ID: build_hidden_contract_definition(),
}


def list_public_contracts() -> list[dict]:
    return [contract for contract in _CONTRACTS.values() if contract.get("public")]


def get_contract(contract_id: str) -> dict | None:
    return _CONTRACTS.get(contract_id)
