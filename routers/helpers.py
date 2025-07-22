import os
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import pyqrcode
from loguru import logger
from quart import Blueprint, request, render_template, flash, session, jsonify

from other.qr_tools import create_beautiful_code
from other.config_reader import start_path
from other.grist_tools import grist_manager, MTLGrist, get_grist_asset_by_code
from other.stellar_tools import check_asset, add_trust_line_uri, xdr_to_uri
from other.stellar_tools import float2str

blueprint = Blueprint('sellers', __name__)
last_update_time = datetime.now() - timedelta(minutes=20)


@blueprint.route('/seller/<account_id>', methods=('GET', 'POST'))
async def cmd_seller(account_id):
    if len(account_id) < 56 or account_id[0] != 'G':
        await flash('BAD public key')
        resp = await render_template('seller.html', memo_text='', sale_sum='')
        return resp

    if request.method == 'POST':
        form_data = await request.form
        sale_sum = form_data['sale_sum']
        memo_text = form_data.get('memo_text')
        if len(sale_sum) < 1:
            await flash('Need more sum')
            resp = await render_template('seller.html', memo_text='', sale_sum='')
            return resp

        sale_sum = float2str(sale_sum)
        if float(sale_sum) <= 0:
            await flash('Need more sum')
            resp = await render_template('seller.html', memo_text='', sale_sum='')
            return resp

        if memo_text and len(memo_text) > 1:
            memo_text = f'&memo={quote_plus(memo_text)}&memo_type=MEMO_TEXT'
        else:
            memo_text = ''

        qr_text = (f'web+stellar:pay?destination={account_id}&amount={sale_sum}'
                   f'&asset_code=EURMTL&asset_issuer=GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V'
                   f'{memo_text}')

        qr_img = f'/static/qr/{uuid.uuid4().hex}.svg'
        qr = pyqrcode.create(qr_text)
        qr.svg(start_path + qr_img, scale=6)

        resp = await render_template('seller.html', memo_text='', sale_sum='',
                                     qr_text=qr_text, qr_img=qr_img)
        return resp

    resp = await render_template('seller.html', memo_text='', sale_sum='')
    return resp


@blueprint.route('/asset/<asset_code>', methods=('GET', 'POST'))
async def cmd_asset(asset_code):
    # Инициализируем переменные по умолчанию
    asset_issuer = None
    qr_text = None
    qr_img = None
    asset_data = None

    if len(asset_code) < 3:
        await flash('BAD asset code')
        asset_code = None
    else:
        # Используем кэширующую функцию вместо прямого обращения к Grist
        asset_data = await get_grist_asset_by_code(asset_code)

        if asset_data:
            asset_issuer = asset_data['issuer']
            asset_code = asset_data['code']

            qr_text = add_trust_line_uri(asset_issuer, asset_code, asset_issuer)
            qr_img = f'/static/qr/{asset_code}.png'
            # если файл не существует, то создаем его
            if not os.path.exists(start_path + qr_img):
                create_beautiful_code(qr_img, asset_code, qr_text)
        else:
            await flash('BAD asset code')
            asset_code = None

    return await render_template('tabler_asset.html',
                                 asset_code=asset_code,
                                 asset_issuer=asset_issuer,
                                 qr_text=qr_text,
                                 qr_img=qr_img,
                                 asset_data=asset_data)


@blueprint.route('/uri', methods=('GET', 'POST'))
async def cmd_uri():
    # if exist GET data xdr
    xdr = request.args.get('xdr')
    try:
        uri_xdr = xdr_to_uri(xdr) if xdr else None
    except Exception as ex:
        await flash('BAD XDR')
        uri_xdr = None
        logger.info(f'cmd_uri: {ex} \n XDR:{xdr}\n')
    resp = await render_template('uri.html', xdr=xdr, uri_xdr=uri_xdr)
    return resp


@blueprint.route('/generate', methods=('GET', 'POST'))
async def cmd_generate():
    return await render_template('generate.html')


if __name__ == '__main__':
    pass
