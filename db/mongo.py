import asyncio
from datetime import datetime
from typing import Optional, List, Dict

from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import Model, Field, Reference, query, AIOEngine, EmbeddedModel
from pydantic import BaseModel

from other.config_reader import config

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

class MongoUser(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str]
    full_name: str
    is_admin: bool = False
    created_at: datetime
    left_at: Optional[datetime] = None

class MongoChat(BaseModel):
    chat_id: int
    username: Optional[str] = None
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    users: Dict[str, MongoUser] = Field(default_factory=dict)
    admins: List[int] = Field(default_factory=list)


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

async def get_all_chats_by_user(user_id: int) -> List[MongoChat]:
    """Получить все чаты, в которых участвует пользователь
    
    Args:
        user_id: ID пользователя в Telegram
        
    Returns:
        Список объектов MongoChat с информацией о чатах
        [MongoChat(chat_id=-1001797244, username=None, title='MTL – РП', created_at=None, last_updated=None, users={'6227392660': MongoUser(user_id=None, username='dec',
        
    Raises:
        ValueError: Если коллекция чатов не существует
        Exception: При ошибках выполнения запроса
    """
    try:
        # Проверяем существование коллекции
        db_name = engine.database.name
        if "chats" not in await engine.client[db_name].list_collection_names():
            raise ValueError("Collection 'chats' does not exist")

        # Формируем запрос: ищем чаты, где есть пользователь с заданным ID
        query = {f"users.{user_id}": {"$exists": True}}

        # Оптимизированная проекция
        projection = {
            "chat_id": 1,
            "title": 1,
            "username": 1,
            f"users.{user_id}": 1,
        }

        # Выполняем запрос к коллекции с проекцией
        chats_cursor = engine.client[db_name].chats.find(query, projection)
        chats_list = await chats_cursor.to_list(length=None)

        # Конвертируем результаты в объекты MongoChat
        return [MongoChat(**chat) for chat in chats_list]

    except Exception as e:
        # Логируем ошибку
        print(f"Error in get_all_chats_by_user: {str(e)}")
        raise


if __name__ == "__main__":
    # Пример использования:
    asset = asyncio.run(get_all_chats_by_user(62260))
    if asset:
        print(f"Found asset: {asset}")
    else:
        print("Asset not found")
