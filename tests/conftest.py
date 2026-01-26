"""
Pytest configuration and shared fixtures.

This file imports all fixtures from the fixtures package.
For better organization, fixtures are split into separate modules:
- fixtures/constants.py: Test constants
- fixtures/app.py: Quart application fixtures
- fixtures/horizon.py: Stellar Horizon mock server
- fixtures/database.py: SQLite in-memory database fixtures

All fixtures are available to tests automatically via pytest's fixture discovery.
"""

import pytest

# Import all fixture modules to make them available to tests
from tests.fixtures.app import app, client
from tests.fixtures.database import (
    async_engine,
    db_session,
    db_pool,
    seed_signers,
    seed_transactions,
    seed_signatures,
    seed_alerts,
)
from tests.fixtures.horizon import (
    horizon_server_config,
    mock_horizon,
    HorizonMockState,
    get_free_port,
)
from tests.fixtures.constants import *

# Make fixtures available at module level
__all__ = [
    "app",
    "client",
    "async_engine",
    "db_session",
    "db_pool",
    "seed_signers",
    "seed_transactions",
    "seed_signatures",
    "seed_alerts",
    "horizon_server_config",
    "mock_horizon",
    "HorizonMockState",
    "get_free_port",
]
