import os

from environs import Env
from pydantic import SecretStr
from pydantic_settings import BaseSettings
from quart import session

env = Env()
env.read_env()

start_path = os.path.dirname(os.path.dirname(__file__))
dotenv_path = os.path.join(start_path, '.env')


class Settings(BaseSettings):
    db_dsn: str
    secret_key: SecretStr
    eurmtl_key: SecretStr
    mmwb_token: SecretStr
    domain: str
    domain_account_id: str
    domain_key: SecretStr
    skynet_token: SecretStr
    cloudflare_secret_key: SecretStr
    yandex_secret_key: SecretStr
    sentry_dsn: str
    mongo_dsn: str
    mongo_db_name: str
    test_user_id: int
    test_mode: bool = False
    grist_token: str

    class Config:
        env_file = dotenv_path
        env_file_encoding = 'utf-8'


config = Settings()


def update_test_user():
    if env.str('ENVIRONMENT', 'test') == 'production':
        config.test_mode = False
    else:
        config.test_mode = True
        data = {
            'id': config.test_user_id,
            'username': "itolstov",
            'photo_url': "https://yastatic.net/s3/home/div/new_app/bender/weather/weather_new_2023/bkn_n.svg",
        }
        session['userdata'] = data
        session["user_id"] = data["id"]
