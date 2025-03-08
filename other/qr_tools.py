from other.config_reader import start_path
import qrcode
from PIL import ImageDraw, Image, ImageFont


def create_beautiful_code(file_name, logo_text, qr_text):
    logo_img = create_image_with_text(logo_text)
    qr_with_logo_img = create_qr_with_logo(qr_text, logo_img)
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
