import pyqrcode
import uuid
from quart import Blueprint, request, make_response, render_template, flash
from config_reader import start_path
from db.pool import db_pool
from db.requests import db_get_dict, EURMTLDictsType
from utils import float2str, add_trust_line_uri, xdr_to_uri
from urllib.parse import quote_plus

blueprint = Blueprint('sellers', __name__)


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

    assets = db_get_dict(db_pool(), EURMTLDictsType.Assets)

    if asset_code in assets:
        qr_text = add_trust_line_uri(assets[asset_code], asset_code, assets[asset_code])
        # (f'web+stellar:tx?xdr={quote_plus(add_asset(assets[asset_code], asset_code, assets[asset_code]))}'
        #            # f'&callback={quote_plus(f"https://eurmtl.me/sign_tools/{transaction.hash}")}'
        #            f'&msg={quote_plus(f"Add trustline for {asset_code}")}'
        #            # f'&pubkey=GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI'
        #            f"{quote_plus('&replace=sourceAccount:X,seqNum:Y;X:account on which to create the trustline,Y:actual seqNum')}"
        #            f'&origin_domain=eurmtl.me')
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
    #print(xdr)
    uri_xdr = xdr_to_uri(xdr) if xdr else None
    resp = await render_template('uri.html', xdr=xdr, uri_xdr=uri_xdr)
    return resp
