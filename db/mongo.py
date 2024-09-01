import asyncio
from datetime import datetime
from typing import Optional, List, Dict

from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import Model, Field, Reference, query, AIOEngine, EmbeddedModel

from config.config_reader import config

# https://art049.github.io/odmantic/

client = AsyncIOMotorClient(config.mongo_dsn)
engine = AIOEngine(client=client, database=config.mongo_db_name)


class User(Model):
    telegram_id: int
    # telegram_id: int = Field(ge=0, custom_type=Int64)
    username: Optional[str] = None
    auth_data: dict = Field(default_factory=dict)
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    stellar: List[str] = Field(default_factory=list)
    mtl_id: Optional[int] = None

    @classmethod
    async def find_by_telegram_id(cls, telegram_id):
        return await engine.find_one(cls, query.or_(
            cls.telegram_id == str(telegram_id),
            cls.telegram_id == int(telegram_id)
        ))

    @classmethod
    async def find_by_stellar_id(cls, stellar_id: str):
        return await engine.find_one(cls, cls.stellar == stellar_id)

    model_config = {
        "collection": "users",
        "parse_doc_with_default_factories": True
    }


class Asset(Model):
    name: str
    code: Optional[str] = None
    issuer: Optional[str] = None
    need_eurmtl: Optional[bool] = False
    need_history: Optional[bool] = False

    description: Optional[str] = None
    status: Optional[str] = None
    stellar: Optional[str] = None
    domain: Optional[str] = None
    contract: Optional[str] = None
    QR: Optional[str] = None
    e_rate: Optional[float] = None
    person: Optional[str] = None
    chat: Optional[str] = None
    b_rate: Optional[float] = None
    MTL_fund: Optional[float] = None

    model_config = {
        "collection": "assets",
        "parse_doc_with_default_factories": True
    }


class Signer(EmbeddedModel):
    weight: int
    key: str


class Balance(EmbeddedModel):
    balance: str
    liquidity_pool_id: Optional[str] = None
    asset: Optional[str] = None


class Account(Model):
    account_id: str
    alias: Optional[str] = None
    descr: Optional[str] = None
    status: Optional[str] = None
    stellar: Optional[str] = None
    need_history: Optional[bool] = False
    need_eurmtl: Optional[bool] = False
    balances: Optional[List[Balance]] = Field(default_factory=list)
    signers: Optional[List[Signer]] = Field(default_factory=list)
    data: Optional[Dict[str, str]] = Field(default_factory=dict)
    last_update: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "collection": "accounts",
        "parse_doc_with_default_factories": True
    }


class Log(Model):
    user: User = Reference()
    action: str
    collection_name: str
    item_id: str
    timestamp: float
    changes: str

    model_config = {
        "collection": "logs"
    }


async def get_asset_by_code(code: str, need_eurmtl=False):
    return await engine.find_one(
        Asset,
        query.and_(
            Asset.code == code,
            Asset.need_eurmtl == True
        )
    )


async def get_all_assets(need_eurmtl_value: bool):
    assets = await engine.find(
        Asset,
        Asset.need_eurmtl == need_eurmtl_value
    )
    return assets


async def get_all_accounts(need_eurmtl_value: bool):
    accounts = await engine.find(
        Account,
        Account.need_eurmtl == need_eurmtl_value
    )
    return accounts


if __name__ == "__main__":
    # Пример использования:
    asset = asyncio.run(User.find_by_stellar_id("GDMBM7P2ZVD64DSMQJIR67CZFWU7EQRI4YMRLZ2XOYT3V7YUBGZ4RXHF"))
    if asset:
        print(f"Found asset: {asset}")
    else:
        print("Asset not found")
