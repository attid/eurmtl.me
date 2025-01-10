import os
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import pyqrcode
import qrcode
from PIL import ImageDraw, Image, ImageFont
from loguru import logger
from quart import Blueprint, request, render_template, flash

from config.config_reader import start_path
from db.mongo import get_asset_by_code
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
    asset = await get_asset_by_code(asset_code, True)
    if asset:
        qr_text = add_trust_line_uri(asset.issuer, asset.code, asset.issuer)
        qr_img = f'/static/qr/{asset_code}.png'
        # если файл не существует, то создаем его
        if not os.path.exists(start_path + qr_img):
            create_beautiful_code(qr_img, asset_code, qr_text)

        resp = await render_template('tabler_asset.html', asset_code=asset_code,
                                     asset_issuer=asset.issuer, qr_text=qr_text, qr_img=qr_img)
        return resp

    else:
        await flash('BAD asset code')

    resp = await render_template('tabler_asset.html')
    return resp


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


def create_beautiful_code(file_name, text, link):
    logo_img = create_image_with_text(text)
    qr_with_logo_img = create_qr_with_logo(link, logo_img)
    qr_with_logo_img.save(start_path + file_name)


def create_qr_with_logo(qr_code_text, logo_img):
    # Создание QR-кода
    qr = qrcode.QRCode(
        version=5,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=5,
        border=1
    )
    qr.add_data(qr_code_text)
    qr.make(fit=True)
    qr_code_img = qr.make_image(fill_color=decode_color('5A89B9')).convert('RGB')

    # Размещение логотипа в центре QR-кода
    pos = ((qr_code_img.size[0] - logo_img.size[0]) // 2 + 5, (qr_code_img.size[1] - logo_img.size[1]) // 2)
    qr_code_img.paste(logo_img, pos)

    return qr_code_img


def create_image_with_text(text, font_path='DejaVuSansMono.ttf', font_size=30, image_size=(200, 50)):
    # Создание пустого изображения
    image = Image.new('RGB', image_size, color='white')
    draw = ImageDraw.Draw(image)

    # Загрузка шрифта
    font = ImageFont.truetype(font_path, font_size)

    # Расчет позиции для размещения текста по центру с использованием textbbox
    textbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = textbox[2] - textbox[0], textbox[3] - textbox[1]
    x = (image_size[0] - text_width) / 2
    y = (image_size[1] - text_height) / 2 - 5

    draw.text((x, y), text, font=font, fill=decode_color('C1D9F9'))

    # Размещение рамки
    xy = [0, 0, image_size[0] - 1, image_size[1] - 1]
    draw.rectangle(xy, outline=decode_color('C1D9F9'), width=2)

    return image


def decode_color(color):
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


@blueprint.route('/generate', methods=('GET', 'POST'))
async def cmd_generate():
    return await render_template('generate.html')


if __name__ == '__main__':
    pass
