import os
from pydantic import SecretStr
from pydantic_settings import BaseSettings

start_path = os.path.dirname(__file__)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')


class Settings(BaseSettings):
    db_dns: str
    secret_key: SecretStr
    eurmtl_key: SecretStr
    bot_token: SecretStr
    signing_key: SecretStr
    skynet_token: SecretStr
    sentry_dsn: str

    class Config:
        env_file = dotenv_path
        env_file_encoding = 'utf-8'


config = Settings()
