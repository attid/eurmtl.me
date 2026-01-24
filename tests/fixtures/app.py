"""
Fixtures for Quart application and test client.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from quart import Quart
from .constants import TEST_SECRET_KEY


@pytest.fixture
def app():
    """
    Create a test Quart application with all blueprints registered.

    This fixture provides a fully configured app for testing with:
    - All blueprints registered
    - Mocked database pool
    - Test configuration
    """
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
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    template_folder = os.path.join(root_path, "templates")
    static_folder = os.path.join(root_path, "static")

    app = Quart(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config["SECRET_KEY"] = TEST_SECRET_KEY

    # Register blueprints
    # Note: remote_sep07_bp is registered by remote_bp
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
    """
    Create a test client from the app fixture.

    Usage:
        async def test_endpoint(client):
            response = await client.get("/")
            assert response.status_code == 200
    """
    return app.test_client()
