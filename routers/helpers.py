import uuid
import pyqrcode
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from quart import Blueprint, request, render_template, flash
from config_reader import start_path
from db.pool import db_pool
from db.requests import db_get_dict, EURMTLDictsType, db_save_dict
from utils.gspread_utils import gs_get_asset
from utils.stellar_utils import add_trust_line_uri, float2str, xdr_to_uri

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
    if len(asset_code) < 3:
        await flash('BAD asset code')

    global last_update_time
    assets = db_get_dict(db_pool(), EURMTLDictsType.Assets)

    if asset_code not in assets:
        if datetime.now() - last_update_time > timedelta(minutes=15):
            issuer = gs_get_asset(asset_code)
            if issuer:
                assets[asset_code] = issuer
                db_save_dict(db_pool(), EURMTLDictsType.Assets, assets)
            last_update_time = datetime.now()

    if asset_code in assets:
        qr_text = add_trust_line_uri(assets[asset_code], asset_code, assets[asset_code])
        qr_img = f'/static/qr/{uuid.uuid4().hex}.svg'
        qr = pyqrcode.create(qr_text)
        qr.svg(start_path + qr_img, scale=4)

        resp = await render_template('asset.html', asset_code=asset_code, asset_issuer=assets[asset_code],
                                     qr_text=qr_text, qr_img=qr_img)
        return resp

    else:
        await flash('BAD asset code')

    resp = await render_template('asset.html')
    return resp


@blueprint.route('/uri', methods=('GET', 'POST'))
async def cmd_uri():
    # if exist GET data xdr
    xdr = request.args.get('xdr')
    # print(xdr)
    uri_xdr = xdr_to_uri(xdr) if xdr else None
    resp = await render_template('uri.html', xdr=xdr, uri_xdr=uri_xdr)
    return resp
