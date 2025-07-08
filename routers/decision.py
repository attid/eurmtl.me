import uuid

from loguru import logger
from quart import Blueprint, request, render_template, flash, jsonify, session, redirect, abort
from sulguk import SULGUK_PARSE_MODE

from other.config_reader import config
from db.sql_models import Decisions
from db.sql_pool import db_pool
from other.gspread_tools import gs_update_decision, gs_get_last_id, gs_save_new_decision
from other.stellar_tools import check_user_weight
from other.telegram_tools import skynet_bot

blueprint = Blueprint('decision', __name__)

statuses = ("❗️ #active", "☑️ #next", "✅ #done", "🔂 #resign", "‼️ #control", "🔇 #canceled")

if config.test_mode:
    chat_ids = (0, 1837984392, 1837984392, 1837984392)  # -100 test
else:
    chat_ids = (0, 1863399780, 1652080456, 1649743884)  # -100


def get_full_text(status, start_text, links_url, uuid_url, username):
    full_text = [status, start_text.replace('<p><br></p>', ''), '---']

    if links_url[0]:
        full_text.append(f'<a href="{links_url[0][0]}">Первое чтение</a>')
    if links_url[1]:
        full_text.append(f'<a href="{links_url[1][0]}">Второе чтение</a>')
    if links_url[2]:
        full_text.append(f'<a href="{links_url[2][0]}">Третье чтение</a>')

    full_text.append('-')
    full_text.append(f'<a href="http://eurmtl.me/d/{uuid_url}">Edit on eurmtl.me</a>')
    full_text.append(f'Added by {username}')
    return '<br>'.join(full_text)


@blueprint.route('/decision', methods=('GET', 'POST'))
@blueprint.route('/d', methods=('GET', 'POST'))
async def cmd_add_decision():
    question_number, short_subject, reading = '', '', 1
    session['return_to'] = request.url
    inquiry = ('<br>'
               '<b>Предложение:</b> <br><br>'
               '<b>Обоснование:</b> <br><br>'
               '<b>Примечание:</b> <br><br>'
               '<b>Имплементация:</b> <br><br>')

    user_weight = await check_user_weight(False)

    if request.method == 'POST':
        form_data = await request.form
        question_number = form_data['question_number']
        short_subject = form_data['short_subject']
        inquiry = form_data['inquiry']
        status = form_data['status']
        reading = int(form_data['reading'])

        user_weight = await check_user_weight()
        if user_weight > 0:
            with db_pool() as db_session:
                existing_decision = db_session.query(Decisions).filter(Decisions.num == question_number).first()
                if existing_decision:
                    await flash(f'Вопрос с номером {question_number} уже существует. '
                                f'<a href="/d/{existing_decision.uuid}">Редактировать существующий вопрос</a> '
                                f'или создайте новый с другим номером.')
                else:
                    d_uuid = uuid.uuid4().hex

                    username = '@' + session['userdata']['username']

                    text = get_full_text(status, inquiry, [[], [], []], d_uuid, username)
                    try:
                        msg = await skynet_bot.send_message(chat_id=int(f'-100{chat_ids[reading]}'),
                                                            text=text,
                                                            parse_mode=SULGUK_PARSE_MODE,
                                                            disable_web_page_preview=True)
                        message_id = msg.message_id
                    except Exception as e:
                        logger.info(f"Error with telegram publishing: {e}")
                        message_id = None

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
                            des.status = status
                            db_session.add(des)
                            db_session.commit()
                        await flash('Вопрос успешно добавлен.', 'good')
                        return redirect(f'/d/{d_uuid}')

    statuses_list = [(status, "") for status in statuses]
    return await render_template('tabler_decision.html', question_number=question_number,
                                 short_subject=short_subject, inquiry=inquiry, reading=reading, statuses=statuses_list,
                                 user_weight=user_weight)


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

    status = decision.status

    links_url = (db_session.query(Decisions.url).filter(Decisions.num == decision.num, Decisions.reading == 1).first(),
                 db_session.query(Decisions.url).filter(Decisions.num == decision.num, Decisions.reading == 2).first(),
                 db_session.query(Decisions.url).filter(Decisions.num == decision.num, Decisions.reading == 3).first())

    user_weight = await check_user_weight(False)
    if request.method == 'POST':
        user_weight = await check_user_weight()
        if user_weight > 0:
            form_data = await request.form
            question_number = decision.num
            short_subject = form_data['short_subject']
            inquiry = form_data['inquiry']
            reading = int(form_data['reading'])
            username = '@' + session['userdata']['username']
            status = form_data['status']

            # new or update
            # если не меняем чтение то обновление
            if reading == decision.reading:
                with db_pool() as db_session:
                    decision: Decisions = db_session.query(Decisions).filter(Decisions.uuid == decision_id).first()
                    decision.full_text = inquiry
                    decision.status = status
                    db_session.commit()
                    text = get_full_text(status, inquiry, links_url, decision.uuid, decision.username)
                    await skynet_bot.edit_message_text(chat_id=int(f'-100{chat_ids[reading]}'),
                                                       text=text,
                                                       parse_mode=SULGUK_PARSE_MODE,
                                                       disable_web_page_preview=True,
                                                       message_id=decision.url.split('/')[-1])

            # если сменили чтение,
            if reading != decision.reading:
                # но оно есть, то ругаемся.
                if links_url[reading - 1] is not None:
                    await flash('Такое чтение уже существует, редактировать надо по ссылке из него')
                else:
                    new_uuid = uuid.uuid4().hex

                    text = get_full_text(status, inquiry, links_url, new_uuid, username)
                    try:
                        msg = await skynet_bot.send_message(chat_id=int(f'-100{chat_ids[reading]}'),
                                                            text=text,
                                                            parse_mode=SULGUK_PARSE_MODE,
                                                            disable_web_page_preview=True)
                        message_id = msg.message_id
                    except Exception as e:
                        logger.info(f"Error with telegram publishing: {e}")
                        message_id = None

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
                            des.status = status
                            db_session.add(des)
                            db_session.commit()

                        # Nmbr	Name	Text	Author	First	Second	Vote	Sign	Decision
                        # 1     2       3       4       5       6       7       8       9
                        if reading == 2:
                            await gs_update_decision(decision.num, 6, url)
                        if reading == 3:
                            await gs_update_decision(decision.num, 8, url)

                        return redirect(f'/d/{new_uuid}')

    statuses_list = [(status_, "selected" if status_ == status else "") for status_ in statuses]

    return await render_template('tabler_decision.html', question_number=question_number,
                                 statuses=statuses_list, user_weight=user_weight,
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
    pass
    # print(asyncio.run(gs_update_decision(155, 5, 5)))
