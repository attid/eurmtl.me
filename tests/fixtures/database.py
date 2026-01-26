"""
Database fixtures for testing with SQLite in-memory database.

This module provides pytest fixtures for:
- SQLite async engine (in-memory)
- Async database sessions
- Database pool (session factory)
- Seed data for common test scenarios
"""

import json
import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.sql_models import Base, Transactions, Signers, Signatures, Alerts


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """
    Create SQLite in-memory async engine for tests.

    Each test gets a fresh database with all tables created.
    The database is disposed after the test completes.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,  # Set to True for SQL query debugging
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine):
    """
    Async database session for each test.

    Provides a clean session with automatic rollback after test completion.
    Use this fixture when you need direct database access in tests.
    """
    async_session_maker = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()  # Rollback any uncommitted changes


@pytest_asyncio.fixture(scope="function")
async def db_pool(async_engine):
    """
    Session factory (database pool) for tests.

    This mimics the production db_pool behavior.
    Use this fixture for app.db_pool in Quart application tests.
    """
    return async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture
async def seed_signers(db_session):
    """
    Seed test database with 5 signers covering different scenarios.

    Signers:
    1. @admin (tg_id=84131737) - Admin user
    2. @alice (tg_id=12345678) - Regular user
    3. @bob (tg_id=23456789) - Regular user
    4. FaceLess (tg_id=None) - User without Telegram account
    5. @charlie (tg_id=34567890) - Regular user
    """
    signers = [
        Signers(
            id=1,
            tg_id=84131737,
            username="@admin",
            public_key="GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
            signature_hint="a1b2c3d4",
            add_dt=datetime(2024, 1, 1, 10, 0, 0),
        ),
        Signers(
            id=2,
            tg_id=12345678,
            username="@alice",
            public_key="GA" + "A" * 54,
            signature_hint="0eca4cad",
            add_dt=datetime(2024, 1, 2, 11, 30, 0),
        ),
        Signers(
            id=3,
            tg_id=23456789,
            username="@bob",
            public_key="GB" + "B" * 54,
            signature_hint="f1e2d3c4",
            add_dt=datetime(2024, 1, 3, 12, 0, 0),
        ),
        Signers(
            id=4,
            tg_id=None,
            username="FaceLess",
            public_key="GC" + "C" * 54,
            signature_hint="deadbeef",
            add_dt=datetime(2024, 1, 4, 13, 0, 0),
        ),
        Signers(
            id=5,
            tg_id=34567890,
            username="@charlie",
            public_key="GD" + "D" * 54,
            signature_hint="cafe1234",
            add_dt=datetime(2024, 1, 5, 14, 0, 0),
        ),
    ]

    for signer in signers:
        db_session.add(signer)
    await db_session.commit()

    return signers


@pytest_asyncio.fixture
async def seed_transactions(db_session, seed_signers):
    """
    Seed test database with 3 transactions in different states.

    Transactions:
    1. hash='a'*64 - New transaction (state=0), requires signatures
    2. hash='b'*64 - Ready to send (state=1), has all signatures
    3. hash='c'*64 - Already sent (state=2), completed

    Note: Depends on seed_signers to ensure public_keys in JSON are valid.
    """
    # Get public keys from seed_signers for realistic JSON
    alice_pk = seed_signers[1].public_key  # @alice
    bob_pk = seed_signers[2].public_key  # @bob
    faceless_pk = seed_signers[3].public_key  # FaceLess

    transactions = [
        Transactions(
            hash="a" * 64,
            description="Payment 100 EURMTL to treasury account",
            body="AAAAAgAAAABpT1MockXDRBody1",
            uuid="uuid1" + "0" * 27,
            json=json.dumps(
                {
                    alice_pk: {"threshold": 5, "signers": [[alice_pk, 5, "0eca4cad"]]},
                    bob_pk: {"threshold": 5, "signers": [[bob_pk, 5, "f1e2d3c4"]]},
                }
            ),
            state=0,  # new
            stellar_sequence=123456789,
            source_account=alice_pk,
            owner_id=12345678,  # @alice
            add_dt=datetime(2024, 1, 10, 15, 0, 0),
            updated_dt=datetime(2024, 1, 10, 15, 0, 0),
        ),
        Transactions(
            hash="b" * 64,
            description="Multi-signature transaction for account settings update",
            body="AAAAAgAAAABzU2MockXDRBody2",
            uuid="uuid2" + "0" * 27,
            json=json.dumps(
                {bob_pk: {"threshold": 10, "signers": [[bob_pk, 10, "f1e2d3c4"]]}}
            ),
            state=1,  # need_sent
            stellar_sequence=123456790,
            source_account=bob_pk,
            owner_id=23456789,  # @bob
            add_dt=datetime(2024, 1, 11, 16, 0, 0),
            updated_dt=datetime(2024, 1, 11, 17, 30, 0),
        ),
        Transactions(
            hash="c" * 64,
            description="Treasury payment completed",
            body="AAAAAgAAAACx91MockXDRBody3",
            uuid="uuid3" + "0" * 27,
            json=json.dumps(
                {
                    faceless_pk: {
                        "threshold": 5,
                        "signers": [[faceless_pk, 5, "deadbeef"]],
                    }
                }
            ),
            state=2,  # was_send
            stellar_sequence=123456791,
            source_account=faceless_pk,
            owner_id=None,
            add_dt=datetime(2024, 1, 9, 10, 0, 0),
            updated_dt=datetime(2024, 1, 9, 10, 15, 0),
        ),
    ]

    for tx in transactions:
        db_session.add(tx)
    await db_session.commit()

    return transactions


@pytest_asyncio.fixture
async def seed_signatures(db_session, seed_transactions, seed_signers):
    """
    Seed test database with signatures for transactions.

    Signatures:
    - Transaction 'a'*64: 1 signature from @alice, 1 hidden from @bob
    - Transaction 'b'*64: 3 signatures (ready to send)
    - Transaction 'c'*64: 1 signature from FaceLess
    """
    signatures = [
        # Signatures for transaction 'a'*64 (new, partially signed)
        Signatures(
            id=1,
            signature_xdr="AAAAQASignature1MockXDR",
            transaction_hash="a" * 64,
            signer_id=2,  # @alice
            hidden=0,
            add_dt=datetime(2024, 1, 10, 15, 10, 0),
        ),
        Signatures(
            id=2,
            signature_xdr="AAAAQASignature2HiddenMockXDR",
            transaction_hash="a" * 64,
            signer_id=3,  # @bob (HIDDEN)
            hidden=1,
            add_dt=datetime(2024, 1, 10, 15, 15, 0),
        ),
        # Signatures for transaction 'b'*64 (ready to send, all signed)
        Signatures(
            id=3,
            signature_xdr="AAAAQASignature3MockXDR",
            transaction_hash="b" * 64,
            signer_id=2,  # @alice
            hidden=0,
            add_dt=datetime(2024, 1, 11, 16, 10, 0),
        ),
        Signatures(
            id=4,
            signature_xdr="AAAAQASignature4MockXDR",
            transaction_hash="b" * 64,
            signer_id=3,  # @bob
            hidden=0,
            add_dt=datetime(2024, 1, 11, 16, 20, 0),
        ),
        Signatures(
            id=5,
            signature_xdr="AAAAQASignature5MockXDR",
            transaction_hash="b" * 64,
            signer_id=5,  # @charlie
            hidden=0,
            add_dt=datetime(2024, 1, 11, 17, 0, 0),
        ),
        # Signatures for transaction 'c'*64 (sent)
        Signatures(
            id=6,
            signature_xdr="AAAAQASignature6MockXDR",
            transaction_hash="c" * 64,
            signer_id=4,  # FaceLess
            hidden=0,
            add_dt=datetime(2024, 1, 9, 10, 5, 0),
        ),
    ]

    for sig in signatures:
        db_session.add(sig)
    await db_session.commit()

    return signatures


@pytest_asyncio.fixture
async def seed_alerts(db_session, seed_transactions, seed_signers):
    """
    Seed test database with alert subscriptions.

    Alerts:
    - Transaction 'a'*64: @alice and @bob subscribed
    - Transaction 'b'*64: @admin and @charlie subscribed
    """
    alerts = [
        Alerts(id=1, tg_id=12345678, transaction_hash="a" * 64),  # @alice
        Alerts(id=2, tg_id=23456789, transaction_hash="a" * 64),  # @bob
        Alerts(id=3, tg_id=84131737, transaction_hash="b" * 64),  # @admin
        Alerts(id=4, tg_id=34567890, transaction_hash="b" * 64),  # @charlie
    ]

    for alert in alerts:
        db_session.add(alert)
    await db_session.commit()

    return alerts
