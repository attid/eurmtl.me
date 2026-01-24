"""
Pytest configuration and shared fixtures.

This file imports all fixtures from the fixtures package.
For better organization, fixtures are split into separate modules:
- fixtures/constants.py: Test constants
- fixtures/app.py: Quart application fixtures
- fixtures/horizon.py: Stellar Horizon mock server

All fixtures are available to tests automatically via pytest's fixture discovery.
"""

import pytest

# Import all fixture modules to make them available to tests
from tests.fixtures.app import app, client
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
    "horizon_server_config",
    "mock_horizon",
    "HorizonMockState",
    "get_free_port",
]
