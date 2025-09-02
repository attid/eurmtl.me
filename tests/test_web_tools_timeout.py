import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from other.web_tools import http_session_manager


@pytest.mark.asyncio
async def test_get_web_request_timeout(monkeypatch):
    mock_session = MagicMock()
    mock_request = MagicMock(side_effect=asyncio.TimeoutError)
    mock_session.request = mock_request
    monkeypatch.setattr(http_session_manager, 'get_session', AsyncMock(return_value=mock_session))

    response = await http_session_manager.get_web_request('GET', 'http://example.com')
    assert response.status == 408
    assert 'timed out' in response.data.lower()
    assert 'timeout' in mock_request.call_args.kwargs
