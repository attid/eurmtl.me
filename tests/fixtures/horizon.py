"""
Fixtures for Stellar Horizon mock server.
"""

import socket
import random
import pytest
from aiohttp import web
from .constants import (
    HORIZON_PORT_START,
    HORIZON_PORT_END,
    HORIZON_PORT_RETRIES,
    TEST_FUNDED_ACCOUNT,
)


def get_free_port(
    start_port=HORIZON_PORT_START,
    end_port=HORIZON_PORT_END,
    retries=HORIZON_PORT_RETRIES,
):
    """Find a free port for testing."""
    for _ in range(retries):
        port = random.randint(start_port, end_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", port))
            sock.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find a free port in range {start_port}-{end_port}")


@pytest.fixture(scope="function")
def horizon_server_config():
    """Configuration for horizon test server."""
    port = get_free_port()
    return {"host": "localhost", "port": port, "url": f"http://localhost:{port}"}


class HorizonMockState:
    """State manager for mock Horizon server."""

    def __init__(self):
        self.requests = []
        self.accounts = {}
        self.not_found_accounts = set()

    def set_account(self, account_id: str, balances=None, sequence="123456789"):
        """Configure mock account data."""
        self.not_found_accounts.discard(account_id)
        self.accounts[account_id] = {
            "id": account_id,
            "account_id": account_id,
            "sequence": sequence,
            "balances": balances
            or [{"asset_type": "native", "balance": "100.0000000"}],
            "signers": [{"key": account_id, "weight": 1, "type": "ed25519_public_key"}],
            "thresholds": {"low_threshold": 0, "med_threshold": 0, "high_threshold": 0},
            "flags": {
                "auth_required": False,
                "auth_revocable": False,
                "auth_immutable": False,
            },
            "paging_token": account_id,
        }


@pytest.fixture
async def mock_horizon(horizon_server_config):
    """
    Starts a local mock Stellar Horizon server.

    Usage:
        async def test_something(mock_horizon):
            mock_horizon.set_account("GABC...", balances=[...])
            # ... test code ...
    """
    routes = web.RouteTableDef()
    state = HorizonMockState()

    # Default funded account for tests
    state.set_account(TEST_FUNDED_ACCOUNT)

    @routes.get("/accounts/{account_id}")
    async def get_account(request):
        account_id = request.match_info["account_id"]
        state.requests.append(
            {"endpoint": "accounts", "method": "GET", "account_id": account_id}
        )

        if account_id in state.not_found_accounts:
            return web.json_response(
                {
                    "status": 404,
                    "title": "Resource Missing",
                    "detail": "Account not found",
                },
                status=404,
            )

        if account_id in state.accounts:
            return web.json_response(state.accounts[account_id])

        # Return default mock for unknown accounts to avoid breaking tests that expect success
        return web.json_response(
            {
                "id": account_id,
                "account_id": account_id,
                "sequence": "123456789",
                "balances": [{"asset_type": "native", "balance": "100.0000000"}],
                "signers": [
                    {"key": account_id, "weight": 1, "type": "ed25519_public_key"}
                ],
                "thresholds": {
                    "low_threshold": 0,
                    "med_threshold": 0,
                    "high_threshold": 0,
                },
                "flags": {},
                "paging_token": account_id,
            }
        )

    @routes.get("/")
    async def root(request):
        return web.json_response(
            {
                "horizon_version": "mock",
                "core_version": "mock",
                "network_passphrase": "Test SDF Network ; September 2015",
            }
        )

    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(
        runner, horizon_server_config["host"], horizon_server_config["port"]
    )
    await site.start()

    yield state

    await runner.cleanup()
