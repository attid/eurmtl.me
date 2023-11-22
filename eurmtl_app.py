import sentry_sdk
from quart import Quart, render_template

import routers.cup
import routers.decision
import routers.federal
import routers.helpers
import routers.index
import routers.laboratory
import routers.remote
import routers.sign_tools
from config_reader import config
from db.models import Base
from db.pool import engine

app = Quart(__name__)

# app.config['HOME_PATH'] = ''
# assets = Environment(app)
# assets.url = app.static_url_path
# scss = Bundle('css/main.css', filters='cssmin', output='css/main.min.css')
# assets.register('main_css', scss)
# sky say it must be bottom assets.register

app.config['SECRET_KEY'] = config.secret_key.get_secret_value()
app.config["EXPLAIN_TEMPLATE_LOADING"] = False

app.register_blueprint(routers.index.blueprint)
app.register_blueprint(routers.laboratory.blueprint)
app.register_blueprint(routers.federal.blueprint)
app.register_blueprint(routers.sign_tools.blueprint)
app.register_blueprint(routers.helpers.blueprint)
app.register_blueprint(routers.decision.blueprint)
app.register_blueprint(routers.cup.blueprint)
app.register_blueprint(routers.remote.blueprint)

# @app.context_processor
# def inject_assets():
#    return dict(assets=assets)


# locale.setlocale(locale.LC_ALL, 'en_GB.UTF-8')

sentry_sdk.init(
    dsn=config.sentry_dsn,
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
)


@app.route('/updatedb')
async def update_db():
    # Base.metadata.drop_all(engine, tables=[Signatures])
    # DROP TABLE ` t_signatures `
    # session.execute('DROP TABLE t_signatures')
    # session.execute('DROP TABLE t_transactions')
    # session.execute('DROP TABLE t_signers')
    # session.commit()
    Base.metadata.create_all(engine)
    return "OK"


# its test
@app.route('/mmwb')
async def mmwb_tools():
    return await render_template('mmwb_tools.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
