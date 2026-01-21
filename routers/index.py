import asyncio
import os
import signal
import subprocess
import uuid

from sqlalchemy import select
from quart import Blueprint, send_file, request, session, redirect, render_template, current_app

from other.config_reader import config, start_path
from db.sql_models import Signers
from other.stellar_tools import check_user_weight
from other.telegram_tools import check_response
from other.quart_tools import get_ip
from other.tailscale import get_latest_version_package
from loguru import logger

blueprint = Blueprint('index', __name__)


@blueprint.route('/tailscale', methods=('GET', 'POST'))
@blueprint.route('/ts', methods=('GET', 'POST'))
@blueprint.route('/ts.deb', methods=('GET', 'POST'))
async def tailscale_static_redirect_route():
    try:
        file_name = await get_latest_version_package()
        if file_name:
            # Ensure the file exists in the static directory after the call
            static_file_path = os.path.join(start_path, "static", file_name)
            if os.path.exists(static_file_path):
                # Redirect to the static file URL
                return redirect(f"/static/{file_name}", code=302)
            else:
                logger.error(f"File {file_name} not found in static directory after get_latest_version_package call: {static_file_path}")
                return "File not found on server after check.", 404
        else:
            return "Could not retrieve package information.", 500
    except Exception as e:
        logger.info(f"Error in /tailscale static redirect route: {e}")
        return f"An error occurred: {e}", 500


@blueprint.route('/')
async def cmd_index():
    return await render_template('index.html')


@blueprint.route('/mytest', methods=('GET', 'POST'))
async def cmd_mytest():
    return '***'


@blueprint.route('/uuid', methods=('GET', 'POST'))
async def get_uid():
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
    if request.method == 'POST':
        # надо проверить параметр если
        # body: JSON.stringify({type: 'cache'})
        json_data = await request.get_json()
        cache_refresh = json_data and json_data.get('type') == 'cache'

        if (await check_user_weight()) > 0:
            username = '@' + session['userdata']['username']
            if username.lower() == '@itolstov':
                if cache_refresh:
                    from quart import current_app
                    current_app.jinja_env.cache = {}
                    return "Cache refreshed"
                else:
                    cmd = f"/usr/bin/ps -o ppid= -p {os.getpid()}"
                    result = subprocess.run(cmd.split(), stdout=subprocess.PIPE)
                    parent_pid = int(result.stdout.decode('utf-8').strip())

                    # Отправить сигнал SIGTERM родительскому процессу
                    os.kill(parent_pid, signal.SIGTERM)

                    return "Restarting..."
        else:
            return "need authority", 403
    else:
        return await render_template('tabler_restart.html')


@blueprint.route('/authorize')
async def authorize():
    data = {
        'id': request.args.get('id', None),
        'first_name': request.args.get('first_name', None),
        'last_name': request.args.get('last_name', None),
        'username': request.args.get('username', None),
        'photo_url': request.args.get('photo_url', None),
        'auth_date': request.args.get('auth_date', None),
        'hash': request.args.get('hash', None)
    }
    if check_response(data, config.skynet_token.get_secret_value()) and data['username']:
        # Authorize user
        session['userdata'] = data
        session["user_id"] = data["id"]

        async with current_app.db_pool() as db_session:
            result = await db_session.execute(select(Signers).filter(Signers.username == data['username']))
            user = result.scalars().first()
            if user and user.tg_id != data['id']:
                user.tg_id = data['id']
                await db_session.commit()

        return_to_url = session.get('return_to', None)
        if return_to_url:
            return redirect(return_to_url)
        else:
            return redirect('/lab')
    else:
        return 'Authorization failed'


@blueprint.route('/login')
async def login():
    return await render_template('tabler_login.html')


@blueprint.route('/addr')
async def lab_addr():
    return await render_template('tabler_addr.html')


@blueprint.route('/logout')
async def logout():
    session.pop('userdata', None)
    session.pop('user_id', None)
    return redirect('/lab')


@blueprint.route('/verification')
async def verification():
    return await render_template('verification.html')


@blueprint.route('/bor', methods=('GET', 'POST'))
@blueprint.route('/bsn', methods=('GET', 'POST'))
@blueprint.route('/bsn/', methods=('GET', 'POST'))
@blueprint.route('/bsn/<account_id>', methods=('GET', 'POST'))
async def get_bsn(account_id: str = ''):
    return await render_template('bsn.html', account_id=account_id)


@blueprint.route('/myip')
async def myip():
    return await get_ip()
