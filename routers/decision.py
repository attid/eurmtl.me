import asyncio
import uuid
from quart import Blueprint, request, render_template, flash, jsonify, session, redirect, abort

from config_reader import config
from db.models import Decisions
from db.pool import db_pool
from utils.gspread_utils import gs_update_decision, gs_get_last_id, gs_save_new_decision
from utils.stellar_utils import check_user_weight
from utils.telegram_utils import send_telegram_message, edit_telegram_message, convert_html_to_telegram_format

blueprint = Blueprint('decision', __name__)

chat_ids = (0, 1863399780, 1652080456, 1649743884)  # -100


# chat_ids = (0, 1837984392, 1837984392, 1837984392)  # -100 test


def get_bottom_text(links_url, uuid_url, username):
    bottom_text = ['---', ]
    if links_url[0]:
        bottom_text.append(f'<a href="{links_url[0][0]}">Первое чтение</a>')
    if links_url[1]:
        bottom_text.append(f'<a href="{links_url[1][0]}">Второе чтение</a>')
    if links_url[2]:
        bottom_text.append(f'<a href="{links_url[2][0]}">Третье чтение</a>')

    bottom_text.append('-')
    bottom_text.append(f'<a href="http://eurmtl.me/d/{uuid_url}">Edit on eurmtl.me</a>')
    bottom_text.append(f'Added by {username}')
    return '\n'.join(bottom_text)


@blueprint.route('/decision', methods=('GET', 'POST'))
@blueprint.route('/d', methods=('GET', 'POST'))
async def cmd_add_decision():
    question_number, short_subject, reading = '', '', 1
    session['return_to'] = request.url
    inquiry = '<br><b>Предложение:</b><br><br><b>Обоснование:</b>'

    if request.method == 'POST':
        form_data = await request.form
        question_number = form_data['question_number']
        short_subject = form_data['short_subject']
        inquiry = form_data['inquiry']
        reading = int(form_data['reading'])
        tg_inquiry = convert_html_to_telegram_format(inquiry)

        user_weight = await check_user_weight()
        # for testing
        # user_weight = 5
        # session['userdata'] = {'username': 'iTolstov'}
        # end for
        if user_weight > 0:

            d_uuid = uuid.uuid4().hex

            username = '@' + session['userdata']['username']
            bottom_text = (f'\n---\n'
                           f'<a href="http://eurmtl.me/d/{d_uuid}">Edit on eurmtl.me</a>'
                           f'Added by {username}')

            message_id = send_telegram_message(f'-100{chat_ids[reading]}', f'{tg_inquiry}{bottom_text}')
            if message_id is None:
                await flash('Error with telegram publishing')
            else:
                url = f'https://t.me/c/{chat_ids[reading]}/{message_id}'

                await gs_save_new_decision(decision_id=question_number, url=url, username=username,
                                           short_name=short_subject)

                with db_pool() as db_session:
                    des = Decisions()
                    des.uuid = d_uuid
                    des.num = question_number
                    des.description = short_subject
                    des.reading = reading
                    des.full_text = inquiry
                    des.url = url
                    des.username = username
                    db_session.add(des)
                    db_session.commit()
                return redirect(f'/d/{d_uuid}')
    # resp = await make_response()
    return await render_template('decision.html', question_number=question_number,
                                 short_subject=short_subject, inquiry=inquiry, reading=reading)


@blueprint.route('/d/<decision_id>', methods=('GET', 'POST'))
async def cmd_show_decision(decision_id):
    session['return_to'] = request.url
    if len(decision_id) != 32:
        abort(404)

    with db_pool() as db_session:
        decision: Decisions = db_session.query(Decisions).filter(Decisions.uuid == decision_id).first()

    if decision is None:
        return 'Decision not exist =('

    question_number, short_subject, inquiry, reading = decision.num, decision.description, decision.full_text, decision.reading

    links_url = (db_session.query(Decisions.url).filter(Decisions.num == decision.num, Decisions.reading == 1).first(),
                 db_session.query(Decisions.url).filter(Decisions.num == decision.num, Decisions.reading == 2).first(),
                 db_session.query(Decisions.url).filter(Decisions.num == decision.num, Decisions.reading == 3).first())

    if request.method == 'POST':
        user_weight = await check_user_weight()
        # for testing
        # user_weight = 5
        # session['userdata'] = {'username': 'iTolstov'}
        # end for

        if user_weight > 0:
            form_data = await request.form
            question_number = decision.num
            short_subject = form_data['short_subject']
            inquiry = form_data['inquiry']
            reading = int(form_data['reading'])
            tg_inquiry = convert_html_to_telegram_format(inquiry)
            username = '@' + session['userdata']['username']

            # new or update
            # если не меняем чтение то обновление
            if reading == decision.reading:
                with db_pool() as db_session:
                    decision: Decisions = db_session.query(Decisions).filter(Decisions.uuid == decision_id).first()
                    decision.full_text = inquiry
                    db_session.commit()
                    edit_telegram_message(chat_id=f'-100{chat_ids[reading]}',
                                          text=f'{tg_inquiry}\n'
                                               f'{get_bottom_text(links_url, decision.uuid, decision.username)}',
                                          message_id=decision.url.split('/')[-1])

            # если сменили чтение,
            if reading != decision.reading:
                # но оно есть, то ругаемся.
                if links_url[reading - 1] is not None:
                    await flash('Такое чтение уже существует, редактировать надо по ссылке из него')
                else:
                    new_uuid = uuid.uuid4().hex

                    message_id = send_telegram_message(f'-100{chat_ids[reading]}',
                                                       f'{tg_inquiry}\n{get_bottom_text(links_url, new_uuid, username)}')
                    if message_id is None:
                        await flash('Error with telegram publishing')
                    else:
                        url = f'https://t.me/c/{chat_ids[reading]}/{message_id}'

                        with db_pool() as db_session:
                            des = Decisions()
                            des.uuid = new_uuid
                            des.num = decision.num
                            des.description = short_subject
                            des.reading = reading
                            des.full_text = inquiry
                            des.url = url
                            des.username = username
                            db_session.add(des)
                            db_session.commit()

                        # Nmbr	Name	Text	Author	First	Second	Vote	Sign	Decision
                        # 1     2       3       4       5       6       7       8       9
                        if reading == 2:
                            await gs_update_decision(decision.num, 6, url)
                        if reading == 3:
                            await gs_update_decision(decision.num, 8, url)

                        return redirect(f'/d/{new_uuid}')

    return await render_template('decision.html', question_number=question_number,
                                 short_subject=short_subject, inquiry=inquiry, reading=reading, links_url=links_url)


@blueprint.route('/decision/number', methods=('GET', 'POST'))
async def cmd_get_number_decision():
    number = await gs_get_last_id()
    return jsonify({'number': str(number[0] + 1)})


@blueprint.route('/decision/update_text', methods=['POST'])
async def update_decision_text():
    if request.method == 'POST':
        # Проверка API ключа
        api_key = request.headers.get('Authorization')
        if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
            return jsonify({"message": "Unauthorized"}), 401

        # Получение данных из запроса
        data = await request.get_json()
        msg_url = data.get('msg_url')
        msg_text = data.get('msg_text')

        if not msg_url or not msg_text:
            return jsonify({"message": "Missing data"}), 400

        # Обновление текста в базе данных
        with db_pool() as db_session:
            decision = db_session.query(Decisions).filter(Decisions.url == msg_url).first()

            if decision is not None:
                decision.full_text = msg_text
                db_session.commit()
                return jsonify({"message": "Text updated successfully"}), 200
            else:
                return jsonify({"message": "Decision not found"}), 404


if __name__ == "__main__":
    print(asyncio.run(gs_update_decision(155, 5, 5)))
