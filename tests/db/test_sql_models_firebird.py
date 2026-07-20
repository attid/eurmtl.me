from sqlalchemy import insert
from sqlalchemy_firebird_async.firebird_driver import AsyncFirebirdDialect

from db.sql_models import Decisions, Transactions


def test_transactions_text_fields_bind_as_firebird_text_blobs():
    stmt = insert(Transactions).values(
        hash="8a5ae51261b0a8ec44ef027aef5aaf94da5c39179e3c36a86194f49472e1d4b4",
        description="Test transaction",
        body="A" * 8880,
        uuid="u" * 32,
        json="{}",
        state=0,
        stellar_sequence=1,
        source_account="G" + "A" * 55,
        owner_id=1,
    )

    sql = str(stmt.compile(dialect=AsyncFirebirdDialect()))

    assert "CAST(:description AS BLOB SUB_TYPE TEXT)" in sql
    assert "CAST(:body AS BLOB SUB_TYPE TEXT)" in sql
    assert "CAST(:json AS BLOB SUB_TYPE TEXT)" in sql
    assert "CAST(:body AS VARCHAR(2000))" not in sql


def test_decisions_full_text_binds_as_firebird_text_blob():
    stmt = insert(Decisions).values(
        uuid="5a5bf53692264ef2bf7d027b8aac9c18",
        description="Об укрупнении пакета GZC",
        full_text="A" * 2598,
        num=683,
        reading=1,
        url="https://t.me/c/1863399780/383",
        username="@KorbVV",
        status="❗️ #active",
    )

    sql = str(stmt.compile(dialect=AsyncFirebirdDialect()))

    assert "CAST(:full_text AS BLOB SUB_TYPE TEXT)" in sql
    assert "CAST(:full_text AS VARCHAR(2000))" not in sql
