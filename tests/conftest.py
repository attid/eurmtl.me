
import pytest
import socket
import random
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from quart import Quart

@pytest.fixture(scope="function")
def horizon_server_config():
    port = get_free_port()
    return {"host": "localhost", "port": port, "url": f"http://localhost:{port}"}

def get_free_port(start_port=8000, end_port=9000, retries=10):
    for _ in range(retries):
        port = random.randint(start_port, end_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find a free port in range {start_port}-{end_port}")

@pytest.fixture
async def mock_horizon(horizon_server_config):
    """
    Starts a local mock Stellar Horizon server.
    """
    routes = web.RouteTableDef()

    class HorizonMockState:
        def __init__(self):
            self.requests = []
            self.accounts = {}
            self.not_found_accounts = set()

        def set_account(self, account_id: str, balances=None, sequence="123456789"):
            self.not_found_accounts.discard(account_id)
            self.accounts[account_id] = {
                "id": account_id,
                "account_id": account_id,
                "sequence": sequence,
                "balances": balances or [{"asset_type": "native", "balance": "100.0000000"}],
                "signers": [{"key": account_id, "weight": 1, "type": "ed25519_public_key"}],
                "thresholds": {"low_threshold": 0, "med_threshold": 0, "high_threshold": 0},
                "flags": {"auth_required": False, "auth_revocable": False, "auth_immutable": False},
                "paging_token": account_id
            }

    state = HorizonMockState()
    # Default funded account for tests
    state.set_account("GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI")

    @routes.get("/accounts/{account_id}")
    async def get_account(request):
        account_id = request.match_info['account_id']
        state.requests.append({"endpoint": "accounts", "method": "GET", "account_id": account_id})

        if account_id in state.not_found_accounts:
            return web.json_response({"status": 404, "title": "Resource Missing", "detail": "Account not found"}, status=404)

        if account_id in state.accounts:
            return web.json_response(state.accounts[account_id])
            
        # Return default mock for unknown accounts to avoid breaking tests that expect success
        return web.json_response({
            "id": account_id,
            "account_id": account_id,
            "sequence": "123456789",
            "balances": [{"asset_type": "native", "balance": "100.0000000"}],
            "signers": [{"key": account_id, "weight": 1, "type": "ed25519_public_key"}],
            "thresholds": {"low_threshold": 0, "med_threshold": 0, "high_threshold": 0},
            "flags": {},
            "paging_token": account_id
        })

    @routes.get("/")
    async def root(request):
        return web.json_response({
            "horizon_version": "mock",
            "core_version": "mock",
            "network_passphrase": "Test SDF Network ; September 2015"
        })

    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, horizon_server_config["host"], horizon_server_config["port"])
    await site.start()

    yield state

    await runner.cleanup()

import os

@pytest.fixture
def app():
    from routers.remote_sep07 import blueprint as remote_sep07_bp
    from routers.index import blueprint as index_bp
    from routers.sign_tools import blueprint as sign_tools_bp
    from routers.cup import blueprint as cup_bp
    from routers.laboratory import blueprint as lab_bp
    from routers.decision import blueprint as decision_bp
    from routers.mmwb import blueprint as mmwb_bp
    from routers.federal import blueprint as federal_bp
    from routers.grist import blueprint as grist_bp
    from routers.rely import blueprint as rely_bp
    from routers.web_editor import blueprint as web_editor_bp
    from routers.helpers import blueprint as helpers_bp
    from routers.remote import blueprint as remote_bp
    
    # Calculate root path
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    template_folder = os.path.join(root_path, 'templates')
    static_folder = os.path.join(root_path, 'static')
    
    app = Quart(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config["SECRET_KEY"] = "test_secret_key"
    
    # app.register_blueprint(remote_sep07_bp) # Registered by remote_bp
    app.register_blueprint(index_bp)
    app.register_blueprint(sign_tools_bp)
    app.register_blueprint(cup_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(decision_bp)
    app.register_blueprint(mmwb_bp)
    app.register_blueprint(federal_bp)
    app.register_blueprint(grist_bp)
    app.register_blueprint(rely_bp)
    app.register_blueprint(web_editor_bp)
    app.register_blueprint(helpers_bp)
    app.register_blueprint(remote_bp)
    
    # Mock db_pool
    app.db_pool = MagicMock()
    app.db_pool.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    app.db_pool.return_value.__aexit__ = AsyncMock(return_value=None)
    
    return app

@pytest.fixture
def client(app):
    return app.test_client()
