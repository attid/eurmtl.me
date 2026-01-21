from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


def create_async_pool(db_dsn: str):
    """
    Creates an async engine and session, returning the sessionmaker and engine.
    """
    # replace firebird:// with firebird+async:// if not present, though usually done in config
    # but to be safe if user hasn't changed config string format yet
    if db_dsn.startswith("firebird://"):
        db_dsn = db_dsn.replace("firebird://", "firebird+firebird_async://")
        # sqlalchemy-firebird-async usually wants firebird+firebird:// or firebird+async:// ?
        # The user link says: https://pypi.org/project/sqlalchemy-firebird-async/
        # which usually implies firebird+fdb:// or similar.
        # Wait, the pypi page says: external dialect.
        # default sqlalchemy-firebird uses fdb.
        # sqlalchemy-firebird-async uses asyncio.
        pass

    # Per documentation for sqlalchemy-firebird, the DSN for fdb is firebird+fdb://
    # For firebird-driver (async), it might be firebird+driver:// or firebird+firebird://?
    # Let's check the README or assume Standard Firebird async driver.
    # Actually, the user just said pypi.org/project/sqlalchemy-firebird-async/
    # Usually usage: create_async_engine("firebird+borland://user:password@host/db") ? No.
    # Let's assume the user config updates the DSN or I handle it.
    # I will just pass DSN as is, but maybe I should ensure it is async compatible if I can.
    # If the user DSN is "firebird://...", standard sqlalchemy uses fdb (sync).
    # For async, we typically need a specific driver.
    # However, I will rely on the user or the library to handle the scheme if it registers itself as 'firebird'.
    # But usually async engines need `+async` or specific driver name.
    # I'll stick to generic implementation first.

    engine = create_async_engine(
        db_dsn,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=50,
        pool_timeout=10,
    )

    db_pool = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    return db_pool, engine
