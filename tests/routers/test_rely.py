import pytest
from unittest.mock import patch

from routers.rely import (
    RELY_GRIST_BASE_URL,
    RELY_GRIST_DOCUMENT_ID,
    GristDealRepository,
    GristDealParticipantRepository,
    GristHolderRepository,
)


def test_rely_repositories_keep_the_separate_grist_binding():
    fake_api = object()

    repositories = [
        GristDealParticipantRepository(fake_api),
        GristHolderRepository(fake_api),
        GristDealRepository(fake_api),
    ]

    assert RELY_GRIST_BASE_URL == "https://mtl-rely.getgrist.com/api/docs"
    assert RELY_GRIST_DOCUMENT_ID == "kceNjvoEEihSsc8dQ5vZVB"
    assert {repository._table_config.base_url for repository in repositories} == {
        RELY_GRIST_BASE_URL
    }
    assert {repository._table_config.access_id for repository in repositories} == {
        RELY_GRIST_DOCUMENT_ID
    }


@pytest.mark.asyncio
async def test_rely_webhook_unauthorized(client):
    """Test /rely/grist-webhook without token"""
    response = await client.post("/rely/grist-webhook", json=[])
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rely_webhook_invalid_token(client):
    """Test /rely/grist-webhook with invalid token"""
    with patch("routers.rely.config") as mock_config:
        mock_config.grist_income = "secret"
        response = await client.post(
            "/rely/grist-webhook", headers={"Authorization": "Bearer wrong"}, json=[]
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_rely_webhook_success(client):
    """Test /rely/grist-webhook success"""
    with patch("routers.rely.config") as mock_config:
        mock_config.grist_income = "secret"
        with patch("routers.rely._process_grist_payload"):
            response = await client.post(
                "/rely/grist-webhook",
                headers={"Authorization": "Bearer secret"},
                json=[{"id": 1}],
            )
            assert response.status_code == 200
            # process task is created in background, tricky to assert it ran without ensuring loop execution
            # but we assert response is 200
