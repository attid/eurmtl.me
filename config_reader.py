import os
from pydantic import BaseSettings, SecretStr

start_path = os.path.dirname(__file__)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')


class Settings(BaseSettings):
    db_dns: str
    secret_key: str

    class Config:
        env_file = dotenv_path
        env_file_encoding = 'utf-8'


config = Settings()
