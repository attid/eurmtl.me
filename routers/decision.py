import asyncio
import os
import gspread_asyncio
import uuid
import requests
from quart import Blueprint, request, make_response, render_template, flash, jsonify, session, redirect, abort
from config_reader import config
from db.models import Signers, Decisions
from db.pool import db_pool
from google.oauth2.service_account import Credentials

from utils import check_user_weight, edit_telegram_message, send_telegram_message

blueprint = Blueprint('decision', __name__)

chat_ids = (0, 1863399780, 1652080456, 1649743884)  # -100


# chat_ids = (0, 1863399780, 1785950216, 1965362401)  # -100 test


def get_creds():
    # To obtain a service account JSON file, follow these steps:
    # https://gspread.readthedocs.io/en/latest/oauth2.html#for-bots-using-service-account
    key_path = os.path.join(os.path.dirname(__file__), 'mtl-google-doc.json')
    # print(start_path, key_path)

    creds = Credentials.from_service_account_file(key_path)
    scoped = creds.with_scopes([
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ])
    return scoped


agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)


def get_bottom_text(links_url, uuid_url):
    bottom_text = ['---', ]
    if links_url[0]:
        bottom_text.append(f'<a href="{links_url[0][0]}">Первое чтение</a>')
    if links_url[1]:
        bottom_text.append(f'<a href="{links_url[1][0]}">Второе чтение</a>')
    if links_url[2]:
        bottom_text.append(f'<a href="{links_url[2][0]}">Третье чтение</a>')

    bottom_text.append('-')
    bottom_text.append(f'<a href="http://eurmtl.me/d/{uuid_url}">Edit on eurmtl.me</a>')
    return '\n'.join(bottom_text)


@blueprint.route('/decision', methods=('GET', 'POST'))
@blueprint.route('/d', methods=('GET', 'POST'))
async def cmd_add_decision():
    question_number, short_subject, inquiry, reading = '', '', '', 1

    if request.method == 'POST':
        form_data = await request.form
        question_number = form_data['question_number']
        short_subject = form_data['short_subject']
        inquiry = form_data['inquiry']
        reading = int(form_data['reading'])

        if (await check_user_weight()) > 0:

            d_uuid = uuid.uuid4().hex

            bottom_text = (f'\n---\n'
                           f'<a href="http://eurmtl.me/d/{d_uuid}">Edit on eurmtl.me</a>')

            message_id = send_telegram_message(f'-100{chat_ids[reading]}', f'{inquiry}{bottom_text}')
            if message_id is None:
                await flash('Error with telegram publishing')
            else:
                url = f'https://t.me/c/{chat_ids[reading]}/{message_id}'

                username = '@' + session['userdata']['username']
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
                    db_session.add(des)
                    db_session.commit()
                return redirect(f'/d/{d_uuid}')
    # resp = await make_response()
    return await render_template('decision.html', question_number=question_number,
                                 short_subject=short_subject, inquiry=inquiry, reading=reading)


@blueprint.route('/d/<decision_id>', methods=('GET', 'POST'))
async def cmd_show_decision(decision_id):
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
        if (await check_user_weight()) > 0:
            form_data = await request.form
            question_number = decision.num
            short_subject = form_data['short_subject']
            inquiry = form_data['inquiry']
            reading = int(form_data['reading'])

            # new or update
            # если не меняем чтение то обновление
            if reading == decision.reading:
                with db_pool() as db_session:
                    decision: Decisions = db_session.query(Decisions).filter(Decisions.uuid == decision_id).first()
                    decision.full_text = inquiry
                    db_session.commit()
                    edit_telegram_message(chat_id=f'-100{chat_ids[reading]}',
                                          text=f'{inquiry}\n{get_bottom_text(links_url, decision.uuid)}',
                                          message_id=decision.url.split('/')[-1])

            # если сменили чтение,
            if reading != decision.reading:
                # но оно есть, то ругаемся.
                if links_url[reading - 1] is not None:
                    await flash('Такое чтение уже существует, редактировать надо по ссылке из него')
                else:
                    new_uuid = uuid.uuid4().hex

                    message_id = send_telegram_message(f'-100{chat_ids[reading]}',
                                                       f'{inquiry}\n{get_bottom_text(links_url, new_uuid)}')
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


async def gs_get_last_id():
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")

    record = await ws.col_values(1)
    return int(record[-1]), len(record)


async def gs_save_new_decision(decision_id, short_name, url, username):
    last_number, last_col = await gs_get_last_id()
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")
    # 155	Обновление голосов  https://t.me/c/1649743884/243	@SomeoneAny
    await ws.update(values=[[decision_id, short_name, url, username]], range_name=f'A{last_col + 1}',
                    value_input_option='USER_ENTERED')
    # await ws.update(f'A{last_col + 1}', [[last_number + 1, datetime.now().strftime('%d.%m'), username, user_id, url,
    #                                      None, None, None, None, None, None, None, None, None, agent_username]],
    #                                      value_input_option='USER_ENTERED')


async def gs_get_decision(decision_id):
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")
    cell = await ws.find(str(decision_id), in_column=0)
    row_number = cell.row
    row_data = await ws.row_values(row_number)
    return row_data
    # ['155', 'Обновление голосов в мультиподписи МТЛ-фонда', 'https://t.me/c/1649743884/243', '@SomeoneAny', '', '', '', '02.10.23', '02.10.23']
    # Nmbr	Name	Text	Author	First	Second	Vote	Sign	Decision


async def gs_update_decision(decision_id, col_id, value):
    # Nmbr	Name	Text	Author	First	Second	Vote	Sign	Decision
    # 1     2       3       4       5       6       7       8       9
    agc = await agcm.authorize()
    ss = await agc.open("MTL_decisions")
    ws = await ss.worksheet("MTLFUND")
    # 155	Обновление голосов  https://t.me/c/1649743884/243	@SomeoneAny
    cell = await ws.find(str(decision_id), in_column=0)
    await ws.update_cell(row=cell.row, col=col_id, value=value)


if __name__ == "__main__":
    print(asyncio.run(gs_update_decision(155, 5, 5)))
