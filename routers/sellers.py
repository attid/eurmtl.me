import uuid
import pyqrcode
from urllib.parse import quote_plus
from flask import Blueprint, render_template, request, make_response, flash
from config.config_reader import start_path
from utils.stellar_utils import float2str

blueprint = Blueprint('sellers', __name__)


@blueprint.route('/seller/<account_id>', methods=('GET', 'POST'))
def seller(account_id):
    if len(account_id) < 56 or account_id[0] != 'G':
        flash('BAD public key')
        resp = make_response(render_template('seller.html', memo_text='', sale_sum=''))
        return resp

    if request.method == 'POST':
        sale_sum = request.form['sale_sum']
        memo_text = request.form.get('memo_text')
        if len(sale_sum) < 1:
            flash('Need more sum')
            resp = make_response(render_template('seller.html', memo_text='', sale_sum=''))
            return resp

        sale_sum = float2str(sale_sum)
        if float(sale_sum) <= 0:
            flash('Need more sum')
            resp = make_response(render_template('seller.html', memo_text='', sale_sum=''))
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

        resp = make_response(render_template('seller.html', memo_text='', sale_sum='',
                                             qr_text=qr_text, qr_img=qr_img))
        return resp

    resp = make_response(render_template('seller.html', memo_text='', sale_sum=''))
    return resp
