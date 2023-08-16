from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config_reader import config

engine = create_engine(
    config.db_dns,
    pool_pre_ping=True,
    pool_size=10,  # базовый размер пула
    max_overflow=50,  # максимальное количество "временных" подключений
    pool_timeout=10  # время ожидания в секундах
)  # Creating DB connections pool

db_pool = sessionmaker(bind=engine)
