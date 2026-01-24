import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_cup_orderbook(client):
    """Test /cup/<asset1>/<asset2>"""
    mock_offers_resp = {'_embedded': {'records': []}}
    
    with patch("routers.cup.Server") as MockServer:
        mock_server = MockServer.return_value
        # Mock sellers
        mock_server.offers.return_value.for_selling.return_value.for_buying.return_value.limit.return_value.call = MagicMock(return_value=mock_offers_resp)
        # Mock buyers
        mock_server.offers.return_value.for_buying.return_value.for_selling.return_value.limit.return_value.call = MagicMock(return_value=mock_offers_resp)
        
        response = await client.get("/cup/XLM/EURMTL-GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_cup_trades(client):
    """Test /cup/trades/<asset1>/<asset2>"""
    mock_trades_resp = {'_embedded': {'records': []}}
    
    with patch("routers.cup.Server") as MockServer:
        mock_server = MockServer.return_value
        mock_server.trades.return_value.for_asset_pair.return_value.limit.return_value.order.return_value.call = MagicMock(return_value=mock_trades_resp)
        
        response = await client.get("/cup/trades/XLM/EURMTL-GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_cup_swap(client):
    """Test /cup/swap/<asset1>/<asset2>"""
    mock_paths_resp = {'_embedded': {'records': []}}
    
    with patch("routers.cup.Server") as MockServer:
        mock_server = MockServer.return_value
        # strict_send_paths
        mock_server.strict_send_paths.return_value.limit.return_value.call = MagicMock(return_value=mock_paths_resp)
        # strict_receive_paths
        mock_server.strict_receive_paths.return_value.limit.return_value.call = MagicMock(return_value=mock_paths_resp)
        
        response = await client.get("/cup/swap/XLM/EURMTL-GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V")
        assert response.status_code == 200
