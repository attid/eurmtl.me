from flask import render_template
from flask_assets import Environment, Bundle
from db.models import Base
from utils import *
from flask import Flask

app = Flask(__name__)
# app.config['HOME_PATH'] = ''
assets = Environment(app)
assets.url = app.static_url_path
scss = Bundle('css/main.css', filters='cssmin', output='css/main.min.css')
assets.register('main_css', scss)

# sky say it must be bottom assets.register
import routers.laboratory
import routers.index
import routers.federal
import routers.sign_tools

app.config['SECRET_KEY'] = config.secret_key.get_secret_value()

app.register_blueprint(routers.index.blueprint)
app.register_blueprint(routers.laboratory.blueprint)
app.register_blueprint(routers.federal.blueprint)
app.register_blueprint(routers.sign_tools.blueprint)

fund_addresses = ('GDX23CPGMQ4LN55VGEDVFZPAJMAUEHSHAMJ2GMCU2ZSHN5QF4TMZYPIS',
                  'GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V')


@app.context_processor
def inject_assets():
    return dict(assets=assets)


# locale.setlocale(locale.LC_ALL, 'en_GB.UTF-8')


@app.route('/updatedb')
def update_db():
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
def mmwb_tools():
    return render_template('mmwb_tools.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
