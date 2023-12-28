import os
import signal
import subprocess
import uuid
from quart import Blueprint, send_file, request, session, redirect

from db.models import Signers
from db.pool import db_pool
from utils.stellar_utils import check_user_weight
from utils.telegram_utils import check_response

blueprint = Blueprint('index', __name__)


@blueprint.route('/')
async def cmd_index():
    text = 'This is a technical domain montelibero.org. ' \
           'You can get more information on the website <a href="https://montelibero.org">montelibero.org</a> ' \
           'or in telegram <a href="https://t.me/Montelibero_org">Montelibero_org</a>' \
           '<br><br><br>' \
           'Это технический домен montelibero.org. ' \
           'Больше информации вы можете получить на сайте <a href="https://montelibero.org">montelibero.org</a> ' \
           'или в телеграм <a href="https://t.me/Montelibero_ru">Montelibero_ru</a>'
    return text


@blueprint.route('/mytest', methods=('GET', 'POST'))
async def cmd_mytest():
    # data = {
    #     'id': 25,
    #     'first_name': 'i',
    #     'last_name': 'l',
    #     'username': 'itolstov',
    #     'photo_url': 'ya.ru',
    #     'auth_date': '010101',
    #     'hash': '321321'
    # }
    # session['userdata'] = data
    return '''
    <body>
        <script async src="https://telegram.org/js/telegram-widget.js?21" 
            data-telegram-login="MyMTLWalletBot" 
            data-size="small" 
            data-auth-url="https://eurmtl.me/login" 
            data-request-access="write">
        </script>
    </body>    
    '''


@blueprint.route('/uuid', methods=('GET', 'POST'))
async def cmd_uuid():
    return uuid.uuid4().hex


@blueprint.route('/err', methods=('GET', 'POST'))
@blueprint.route('/log', methods=('GET', 'POST'))
async def cmd_send_err():
    if (await check_user_weight()) > 0:
        file_name = '/home/eurmtl/hypercorn.log'
        import os
        if os.path.isfile(file_name):
            return await send_file(file_name, mimetype='text/plain')
            # with open(file_name, "r") as f:
            #    text = f.read()
        else:
            return "No error"
    else:
        return "need authority"


@blueprint.route('/restart', methods=('GET', 'POST'))
async def restart():
    if (await check_user_weight()) > 0:
        username = '@' + session['userdata']['username']
        if username.lower() == '@itolstov':
            cmd = f"/usr/bin/ps -o ppid= -p {os.getpid()}"
            result = subprocess.run(cmd.split(), stdout=subprocess.PIPE)
            parent_pid = int(result.stdout.decode('utf-8').strip())

            # Отправить сигнал SIGTERM родительскому процессу
            os.kill(parent_pid, signal.SIGTERM)

            return "Restarting..."


@blueprint.route('/login')
async def login_telegram():
    data = {
        'id': request.args.get('id', None),
        'first_name': request.args.get('first_name', None),
        'last_name': request.args.get('last_name', None),
        'username': request.args.get('username', None),
        'photo_url': request.args.get('photo_url', None),
        'auth_date': request.args.get('auth_date', None),
        'hash': request.args.get('hash', None)
    }
    if check_response(data) and data['username']:
        # Authorize user
        session['userdata'] = data
        with db_pool() as db_session:
            user = db_session.query(Signers).filter(Signers.username == data['username']).first()
            if user and user.tg_id != data['id']:
                user.tg_id = data['id']
                db_session.commit()
        return_to_url = session.get('return_to', None)
        if return_to_url:
            return redirect(return_to_url)
        else:
            return redirect('/lab')
    else:
        return 'Authorization failed'


@blueprint.route('/logout')
async def logout():
    await session.pop('userdata', None)
    return redirect('/lab')
