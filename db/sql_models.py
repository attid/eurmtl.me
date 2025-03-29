import uuid as uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Column, Text, DateTime, create_engine, ForeignKey, BigInteger
from sqlalchemy.orm import declarative_base, sessionmaker

from other.config_reader import config

Base = declarative_base()
metadata = Base.metadata


@dataclass
class User:
    telegram_id: int
    account_id: str
    username: Optional[str] = None
    weight: Optional[int] = None


class Addresses(Base):
    __tablename__ = 't_addresses'
    id = Column(Integer(), primary_key=True)
    stellar_address = Column(String(32), nullable=False)
    account_id = Column(String(56), nullable=False)
    memo = Column(String(32), nullable=True)
    add_dt = Column(DateTime(), default=datetime.now)
    updated_dt = Column(DateTime(), default=datetime.now, onupdate=datetime.now)


class Transactions(Base):
    __tablename__ = 't_transactions'
    hash = Column('hash', String(64), primary_key=True)
    description = Column('description', Text(4000), nullable=False)
    body = Column('body', Text(12000), nullable=False)
    add_dt = Column('add_dt', DateTime(), default=datetime.now)
    updated_dt = Column('updated_dt', DateTime(), default=datetime.now, onupdate=datetime.now)
    uuid = Column('uuid', String(32), default=lambda: uuid.uuid4().hex)
    json = Column('json', Text(), nullable=True)
    state = Column('state', Integer(), default=0)  # 0-new 1-need_sent 2-was_send 3-cancel
    stellar_sequence = Column('stellar_sequence', BigInteger(), nullable=True)
    source_account = Column('source_account', String(56), nullable=True)
    owner_id = Column('owner_id', BigInteger(), nullable=True)


class Signers(Base):
    __tablename__ = 't_signers'
    id = Column('id', Integer(), primary_key=True)
    tg_id = Column('tg_id', BigInteger(), nullable=True)
    username = Column('username', String(32), nullable=False)
    public_key = Column('public_key', String(56), nullable=False)
    signature_hint = Column('signature_hint', String(8), nullable=False)
    add_dt = Column('add_dt', DateTime(), default=datetime.now)


class Signatures(Base):
    __tablename__ = 't_signatures'
    id = Column('id', Integer(), primary_key=True)
    signature_xdr = Column('signature_xdr', String(100), nullable=False)
    transaction_hash = Column('transaction_hash', String(64), ForeignKey('t_transactions.hash'))
    signer_id = Column('signer_id', Integer(), ForeignKey('t_signers.id'))
    add_dt = Column('add_dt', DateTime(), default=datetime.now)
    hidden = Column('hidden', Integer(), default=0)
    # Column('updated_dt', DateTime(), default=datetime.now, onupdate=datetime.now)


# class EurmtlDicts(Base):
#     __tablename__ = 'eurmtl_dicts'
#     id = Column(Integer, primary_key=True)
#     dict_key = Column(String(64), nullable=False)
#     dict_value = Column(String(64), nullable=False)
#     dict_type = Column(Integer, nullable=False)


class Decisions(Base):
    __tablename__ = 't_decisions'
    uuid = Column('uuid', String(64), primary_key=True)
    description = Column('description', String(4000), nullable=False)
    full_text = Column('full_text', Text(12000), nullable=True)
    dt = Column('dt', DateTime(), default=datetime.now)
    num = Column('num', Integer, nullable=False)
    reading = Column('reading', Integer, nullable=False)
    url = Column('url', String(64), nullable=False)
    username = Column(String(64), nullable=False)
    status = Column(String(64), nullable=False)


class Alerts(Base):
    __tablename__ = 't_alerts'
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, nullable=True)
    transaction_hash = Column(String(64), nullable=True)


class WebEditorMessages(Base):
    __tablename__ = 't_web_editor_messages'
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False, default=0)
    message_id = Column(BigInteger, nullable=False, default=0)
    message_text = Column(Text(12000), nullable=False)
    uuid = Column('uuid', String(32))


class WebEditorLogs(Base):
    __tablename__ = 't_web_editor_logs'
    id = Column(Integer, primary_key=True)
    web_editor_message_id = Column(Integer, nullable=False)
    message_text = Column(Text(12000), nullable=False)
    dt = Column(DateTime(), default=datetime.now)


class MMWBTransactions(Base):
    __tablename__ = 't_mmwb_transactions'
    uuid = Column('uuid', String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    tg_id = Column('tg_id', BigInteger(), nullable=True)
    json = Column('json', Text(), nullable=True)
    dt = Column(DateTime(), default=datetime.now)


class Sep6Transactions(Base):
    __tablename__ = 't_sep6_transactions'
    uuid = Column('uuid', String(32), default=lambda: uuid.uuid4().hex, primary_key=True)
    admin_uuid = Column('admin_uuid', String(32), default=lambda: uuid.uuid4().hex)
    kind = Column('kind', String(32), nullable=True)
    started_at = Column('started_at', DateTime(), default=datetime.now)
    completed_at = Column('completed_at', DateTime(), nullable=True)
    amount_in = Column('amount_in', String(32), nullable=True)
    amount_out = Column('amount_out', String(32), nullable=True)
    amount_fee = Column('amount_fee', String(32), nullable=True)
    stellar_transaction_id = Column('stellar_transaction_id', String(64), nullable=True)
    external_transaction_id = Column('external_transaction_id', String(64), nullable=True)


if __name__ == '__main__':
    pass
    engine = create_engine(config.db_dsn, pool_pre_ping=True)
    db_pool = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
