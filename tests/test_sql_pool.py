from unittest.mock import patch

from db.sql_pool import create_async_pool


def test_create_async_pool_rewrites_firebird_scheme():
    with (
        patch(
            "db.sql_pool.create_async_engine", return_value="engine"
        ) as create_engine,
        patch("db.sql_pool.async_sessionmaker", return_value="pool") as sessionmaker,
    ):
        pool, engine = create_async_pool("firebird://user:pass@host/db")

    create_engine.assert_called_once_with(
        "firebird+firebird_async://user:pass@host/db",
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=50,
        pool_timeout=10,
    )
    sessionmaker.assert_called_once()
    assert pool == "pool"
    assert engine == "engine"


def test_create_async_pool_keeps_non_firebird_dsn():
    with (
        patch(
            "db.sql_pool.create_async_engine", return_value="engine"
        ) as create_engine,
        patch("db.sql_pool.async_sessionmaker", return_value="pool"),
    ):
        create_async_pool("sqlite+aiosqlite:///:memory:")

    create_engine.assert_called_once()
    assert create_engine.call_args.args[0] == "sqlite+aiosqlite:///:memory:"
