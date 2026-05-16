import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from quart import session
from sqlalchemy import select

from other.config_reader import config
from db.sql_models import Addresses, Signers


@pytest.mark.asyncio
async def test_federal_federation_name(client, app, db_session):
    """Test /federation?q=name&type=name"""
    address = Addresses(
        stellar_address="test*eurmtl.me",
        account_id="GABC",
        memo=None,
        add_dt=datetime(2024, 1, 1, 0, 0, 0),
        updated_dt=datetime(2024, 1, 1, 0, 0, 0),
    )
    db_session.add(address)
    await db_session.commit()

    @app.before_request
    async def mark_session_permanent():
        session.permanent = True

    response = await client.get("/federation?q=test*eurmtl.me&type=name")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-cache, no-store, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert "Set-Cookie" not in response.headers
    data = await response.get_json()
    assert data["stellar_address"] == "test*eurmtl.me"
    assert data["account_id"] == "GABC"


@pytest.mark.asyncio
async def test_federal_federation_name_prefers_addresses_over_signers(
    client, app, db_session
):
    address = Addresses(
        stellar_address="alice*eurmtl.me",
        account_id="GADDRESS",
        memo=None,
        add_dt=datetime(2024, 1, 1, 0, 0, 0),
        updated_dt=datetime(2024, 1, 1, 0, 0, 0),
    )
    signer = Signers(
        username="@alice",
        public_key="GSIGNER",
        tg_id=123,
        signature_hint="abcd1234",
    )
    db_session.add(address)
    db_session.add(signer)
    await db_session.commit()

    response = await client.get("/federation?q=alice*eurmtl.me&type=name")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["stellar_address"] == "alice*eurmtl.me"
    assert data["account_id"] == "GADDRESS"


@pytest.mark.asyncio
async def test_federal_federation_name_falls_back_to_signer_username(
    client, db_session
):
    signer = Signers(
        username="@Alice",
        public_key="GALICE",
        tg_id=123,
        signature_hint="abcd1234",
    )
    db_session.add(signer)
    await db_session.commit()

    response = await client.get("/federation?q=ALICE*eurmtl.me&type=name")

    assert response.status_code == 200
    assert await response.get_json() == {
        "stellar_address": "alice*eurmtl.me",
        "account_id": "GALICE",
    }


@pytest.mark.asyncio
async def test_federal_federation_id_falls_back_to_signer_public_key(
    client, db_session
):
    signer = Signers(
        username="@Alice",
        public_key="GALICE",
        tg_id=123,
        signature_hint="abcd1234",
    )
    db_session.add(signer)
    await db_session.commit()

    response = await client.get("/federation?q=GALICE&type=id")

    assert response.status_code == 200
    assert await response.get_json() == {
        "stellar_address": f"alice*{config.domain.lower()}",
        "account_id": "GALICE",
    }


@pytest.mark.asyncio
async def test_federal_federation_not_found_uses_sep2_status_and_cors(client, app):
    @app.before_request
    async def mark_session_permanent():
        session.permanent = True

    response = await client.get("/federation?q=missing*eurmtl.me&type=name")

    assert response.status_code == 404
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Cache-Control"] == "no-cache, no-store, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert "Set-Cookie" not in response.headers
    assert await response.get_json() == {"error": "Not found."}


@pytest.mark.asyncio
async def test_federal_stellar_toml(client):
    """Test /.well-known/stellar.toml"""
    response = await client.get("/.well-known/stellar.toml")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/plain"


@pytest.mark.asyncio
async def test_federation_addresses_admin_rejects_non_admin(client):
    with patch("routers.federal.check_user_weight", new=AsyncMock(return_value=0)):
        response = await client.get("/federation/addresses")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_federation_addresses_admin_lists_addresses(client, db_session):
    address = Addresses(
        stellar_address="alice*eurmtl.me",
        account_id="GALICE",
        memo="memo",
        add_dt=datetime(2024, 1, 1, 0, 0, 0),
        updated_dt=datetime(2024, 1, 1, 0, 0, 0),
    )
    db_session.add(address)
    await db_session.commit()

    with patch("routers.federal.check_user_weight", new=AsyncMock(return_value=1)):
        response = await client.get("/federation/addresses")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "alice*eurmtl.me" in body
    assert "GALICE" in body
    assert "memo" in body


@pytest.mark.asyncio
async def test_federation_addresses_admin_creates_lowercase_address(client, db_session):
    with patch("routers.federal.check_user_weight", new=AsyncMock(return_value=1)):
        response = await client.post(
            "/federation/addresses",
            form={
                "action": "create",
                "stellar_address": "Alice*EURMTL.ME",
                "account_id": "GALICE",
                "memo": "",
            },
        )

    assert response.status_code == 302
    result = await db_session.execute(select(Addresses))
    address = result.scalars().one()
    assert address.stellar_address == "alice*eurmtl.me"
    assert address.account_id == "GALICE"
    assert address.memo is None


@pytest.mark.asyncio
async def test_federation_addresses_admin_updates_address(client, db_session):
    address = Addresses(
        stellar_address="alice*eurmtl.me",
        account_id="GALICE",
        memo=None,
        add_dt=datetime(2024, 1, 1, 0, 0, 0),
        updated_dt=datetime(2024, 1, 1, 0, 0, 0),
    )
    db_session.add(address)
    await db_session.commit()

    with patch("routers.federal.check_user_weight", new=AsyncMock(return_value=1)):
        response = await client.post(
            "/federation/addresses",
            form={
                "action": "update",
                "id": str(address.id),
                "stellar_address": "Alice2*EURMTL.ME",
                "account_id": "GALICE2",
                "memo": "new memo",
            },
        )

    assert response.status_code == 302
    await db_session.refresh(address)
    assert address.stellar_address == "alice2*eurmtl.me"
    assert address.account_id == "GALICE2"
    assert address.memo == "new memo"


@pytest.mark.asyncio
async def test_federation_addresses_admin_deletes_address(client, db_session):
    address = Addresses(
        stellar_address="alice*eurmtl.me",
        account_id="GALICE",
        memo=None,
        add_dt=datetime(2024, 1, 1, 0, 0, 0),
        updated_dt=datetime(2024, 1, 1, 0, 0, 0),
    )
    db_session.add(address)
    await db_session.commit()

    with patch("routers.federal.check_user_weight", new=AsyncMock(return_value=1)):
        response = await client.post(
            "/federation/addresses",
            form={"action": "delete", "id": str(address.id)},
        )

    assert response.status_code == 302
    db_session.expire_all()
    result = await db_session.execute(select(Addresses))
    assert result.scalars().first() is None


@pytest.mark.asyncio
async def test_user_dropdown_shows_federation_addresses_link_for_superadmin(client):
    async with client.session_transaction() as test_session:
        test_session["user_id"] = 84131737
        test_session["userdata"] = {"username": "admin", "photo_url": ""}

    response = await client.get("/sign_tools")
    body = await response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/federation/addresses" in body


@pytest.mark.asyncio
async def test_user_dropdown_hides_federation_addresses_link_for_regular_user(client):
    async with client.session_transaction() as test_session:
        test_session["user_id"] = 12345678
        test_session["userdata"] = {"username": "alice", "photo_url": ""}

    response = await client.get("/sign_tools")
    body = await response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/federation/addresses" not in body


@pytest.mark.asyncio
async def test_federal_sep6_info(client):
    """Test /sep6/info"""
    response = await client.get("/sep6/info")
    assert response.status_code == 200
    data = await response.get_json()
    assert "deposit" in data


@pytest.mark.asyncio
async def test_federal_sep10_auth(client):
    """Test /auth (SEP-10)"""
    with patch(
        "routers.federal.build_challenge_transaction", return_value="challenge_xdr"
    ):
        response = await client.get("/auth?account=GABC&home_domain=eurmtl.me")
        assert response.status_code == 200
        data = await response.get_json()
        assert data["transaction"] == "challenge_xdr"
