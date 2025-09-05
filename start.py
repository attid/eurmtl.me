import logging
from datetime import timedelta

import sentry_sdk
from cachetools import TTLCache
from loguru import logger
from quart import Quart, session

import routers.cup
import routers.decision
import routers.federal
import routers.helpers
import routers.index
import routers.laboratory
import routers.mmwb
import routers.remote
import routers.sign_tools
import routers.web_editor
import routers.grist
from other.config_reader import config, update_test_user
from db.sql_models import Base
from db.sql_pool import engine

app = Quart(__name__)

logger.add("log/app.log", level=logging.INFO)

# app.config['HOME_PATH'] = ''
# assets = Environment(app)
# assets.url = app.static_url_path
# scss = Bundle('css/main.css', filters='cssmin', output='css/main.min.css')
# assets.register('main_css', scss)
# sky say it must be bottom assets.register

app.config["SECRET_KEY"] = config.secret_key.get_secret_value()
app.config["EXPLAIN_TEMPLATE_LOADING"] = False
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)


app.register_blueprint(routers.index.blueprint)
app.register_blueprint(routers.laboratory.blueprint)
# app.register_blueprint(routers.federal.blueprint)
app.register_blueprint(routers.federal.cors_enabled_blueprint)
app.register_blueprint(routers.sign_tools.blueprint)
app.register_blueprint(routers.helpers.blueprint)
app.register_blueprint(routers.decision.blueprint)
app.register_blueprint(routers.cup.blueprint)
app.register_blueprint(routers.remote.blueprint)
app.register_blueprint(routers.web_editor.blueprint)
app.register_blueprint(routers.mmwb.blueprint)
app.register_blueprint(routers.grist.blueprint)

# @app.context_processor
# def inject_assets():
#    return dict(assets=assets)


# locale.setlocale(locale.LC_ALL, 'en_GB.UTF-8')

# Создаем TTL кеш: максимум 100 ключей, время жизни ключа - 1 минута
error_cache = TTLCache(maxsize=100, ttl=timedelta(hours=1).total_seconds())


def before_send(event, hint):
    error_type = event.get("exception", {}).get("values", [{}])[0].get("type", "")
    error_value = event.get("exception", {}).get("values", [{}])[0].get("value", "")
    error_key = f"{error_type}:{error_value}"

    if error_key in error_cache:
        # Если ошибка уже в кеше, не отправляем ее снова
        return None

    # Если ошибки нет в кеше, добавляем ее и отправляем событие
    error_cache[error_key] = True
    return event


sentry_sdk.init(
    dsn=config.sentry_dsn,
    traces_sample_rate=0.1,
    profiles_sample_rate=0.1,
    before_send=before_send,
)


@app.route("/updatedb")
async def update_db():
    # Base.metadata.drop_all(engine, tables=[Signatures])
    # DROP TABLE ` t_signatures `
    # session.execute('DROP TABLE t_signatures')
    # session.execute('DROP TABLE t_transactions')
    # session.execute('DROP TABLE t_signers')
    # session.commit()
    Base.metadata.create_all(engine)
    return "OK"


@app.before_request
async def before_request():
    session.permanent = True
    if "userdata" not in session:  # Чтобы избежать перезаписи сессии на каждом запросе
        update_test_user()


@app.before_serving
async def initialize_grist_cache():
    """Инициализация кеша Grist при запуске приложения"""
    from other.grist_cache import grist_cache
    if not config.test_mode:
        await grist_cache.initialize_cache()


if __name__ == "__main__":
    if config.test_mode:
        app.run(host="0.0.0.0", port=8000, debug=True)
    else:
        import uvicorn
        try:
            import uvloop
            uvloop.install()  # Заменяет стандартный event loop
        except ImportError:
            pass  # Если uvloop не установлен, используем стандартный
        uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)

