import asyncio
import uuid
from datetime import datetime

from loguru import logger
from sqlalchemy import select
from quart import (
    Blueprint,
    request,
    render_template,
    flash,
    jsonify,
    session,
    redirect,
    abort,
    current_app,
)
from sulguk import SULGUK_PARSE_MODE

import urllib.parse

from other.config_reader import config
from db.sql_models import Decisions
from other.gspread_tools import gs_update_decision, gs_get_last_id, gs_save_new_decision
from services.stellar_client import check_user_weight
from other.telegram_tools import skynet_bot

blueprint = Blueprint("decision", __name__)

D2_PAGE_SIZE = 20
D2_PAGER_WINDOW = 5
D2_ACTIVE_STATUSES = ("❗️ #active", "☑️ #next", "‼️ #control")


@blueprint.app_template_global()
def d2_pager_url(page):
    args = request.args.to_dict(flat=False)
    args["page"] = [str(page)]
    return f"{request.path}?{urllib.parse.urlencode(args, doseq=True)}"


@blueprint.app_template_global()
def d2_pager_pages(page, total_pages):
    window = D2_PAGER_WINDOW
    start = max(1, min(page - window // 2, total_pages - window + 1))
    return range(start, min(start + window - 1, total_pages) + 1)

statuses = (
    "❗️ #active",
    "☑️ #next",
    "✅ #done",
    "🔂 #resign",
    "‼️ #control",
    "🔇 #canceled",
)

if config.test_mode:
    chat_ids = (0, 1837984392, 1837984392, 1837984392)  # -100 test
else:
    chat_ids = (0, 1863399780, 1652080456, 1649743884)  # -100


def get_full_text(status, start_text, links_url, uuid_url, username):
    full_text = [status, start_text.replace("<p><br></p>", ""), "---"]

    if links_url[0]:
        full_text.append(f'<a href="{links_url[0][0]}">Первое чтение</a>')
    if links_url[1]:
        full_text.append(f'<a href="{links_url[1][0]}">Второе чтение</a>')
    if links_url[2]:
        full_text.append(f'<a href="{links_url[2][0]}">Третье чтение</a>')

    full_text.append("-")
    full_text.append(f'<a href="http://eurmtl.me/d/{uuid_url}">Edit on eurmtl.me</a>')
    full_text.append(f"Added by {username}")
    return "<br>".join(full_text)


@blueprint.route("/decision", methods=("GET", "POST"))
@blueprint.route("/d", methods=("GET", "POST"))
async def cmd_add_decision():
    question_number, short_subject, reading = "", "", 1
    session["return_to"] = request.url
    inquiry = (
        "<br>"
        "<b>Предложение:</b> <br><br>"
        "<b>Обоснование:</b> <br><br>"
        "<b>Примечание:</b> <br><br>"
        "<b>Имплементация:</b> <br><br>"
    )

    user_weight = await check_user_weight(False)

    if request.method == "POST":
        form_data = await request.form
        question_number = form_data["question_number"]
        short_subject = form_data["short_subject"]
        inquiry = form_data["inquiry"]
        status = form_data["status"]
        reading = int(form_data["reading"])

        user_weight = await check_user_weight()
        if user_weight > 0:
            async with current_app.db_pool() as db_session:
                result = await db_session.execute(
                    select(Decisions).filter(Decisions.num == question_number)
                )
                existing_decision = result.scalars().first()
            if existing_decision:
                await flash(
                    f"Вопрос с номером {question_number} уже существует. "
                    f'<a href="/d/{existing_decision.uuid}">Редактировать существующий вопрос</a> '
                    f"или создайте новый с другим номером."
                )
            else:
                d_uuid = uuid.uuid4().hex

                username = "@" + session["userdata"]["username"]

                text = get_full_text(status, inquiry, [[], [], []], d_uuid, username)
                try:
                    msg = await skynet_bot.send_message(
                        chat_id=int(f"-100{chat_ids[reading]}"),
                        text=text,
                        parse_mode=SULGUK_PARSE_MODE,
                        disable_web_page_preview=True,
                    )
                    message_id = msg.message_id
                except Exception as e:
                    logger.info(f"Error with telegram publishing: {e}")
                    message_id = None

                if message_id is None:
                    await flash("Error with telegram publishing")
                else:
                    url = f"https://t.me/c/{chat_ids[reading]}/{message_id}"

                    await gs_save_new_decision(
                        decision_id=question_number,
                        url=url,
                        username=username,
                        short_name=short_subject,
                    )

                    async with current_app.db_pool() as db_session:
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
                        await db_session.commit()
                    await flash("Вопрос успешно добавлен.", "good")
                    return redirect(f"/d/{d_uuid}")

    statuses_list = [(status, "") for status in statuses]
    return await render_template(
        "tabler_decision.html",
        question_number=question_number,
        short_subject=short_subject,
        inquiry=inquiry,
        reading=reading,
        statuses=statuses_list,
        user_weight=user_weight,
    )


@blueprint.route("/d2", methods=("GET",))
async def cmd_d2_index():
    return await render_template("d2_index.html")


async def _load_question_tables():
    """Возвращает (questions, question_data, templates) из Grist."""
    from other.grist_tools import grist_manager, MTLGrist

    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    question_data = await grist_manager.load_table_data(MTLGrist.QUESTION_DATA) or []
    templates = await grist_manager.load_table_data(MTLGrist.QUESTION_TEMPLATES) or []
    return questions, question_data, templates


def _readings_int(row) -> int | None:
    try:
        return int(row.get("READING"))
    except (TypeError, ValueError):
        return None


async def _find_question_row(question_uuid: str):
    """Ищет строку QUESTION_DATA по UUID, возвращает (data_row, question)."""
    questions, question_data, _ = await _load_question_tables()
    row = next((r for r in question_data if r.get("UUID") == question_uuid), None)
    if row is None:
        return None, None
    question = next(
        (q for q in questions if q.get("id") == row.get("QUESTION_ID")), None
    )
    return row, question


def _question_links(question_id: int, question_data: list) -> tuple:
    """TELEGRAM_LINK'и всех чтений вопроса: (first, second, third)."""
    links = [None, None, None]
    for row in question_data:
        if row.get("QUESTION_ID") != question_id:
            continue
        reading = _readings_int(row)
        if reading and 1 <= reading <= 3 and row.get("TELEGRAM_LINK"):
            links[reading - 1] = (row["TELEGRAM_LINK"],)
    return tuple(links)


@blueprint.route("/d2/<question_uuid>", methods=("GET", "POST"))
async def cmd_d2_show(question_uuid):
    session["return_to"] = request.url

    data_row, question = await _find_question_row(question_uuid)
    if data_row is None or question is None:
        return "Decision not exist =("

    questions, question_data, _ = await _load_question_tables()
    links_url = _question_links(question["id"], question_data)

    question_number = question.get("NUMBER")
    short_subject = question.get("TITLE") or ""
    inquiry = data_row.get("BODY") or ""
    reading = _readings_int(data_row) or 1
    status = data_row.get("STATUS") or ""
    username = data_row.get("CREATED_BY") or ""

    user_weight = await check_user_weight(False)
    if request.method == "POST":
        user_weight = await check_user_weight()
        if user_weight > 0:
            form_data = await request.form
            short_subject = form_data["short_subject"]
            inquiry = form_data["inquiry"]
            status = form_data["status"]
            new_reading = int(form_data["reading"])

            from other.grist_tools import grist_manager, MTLGrist

            same_reading = new_reading == reading
            reading_exists = links_url[new_reading - 1] is not None

            if not same_reading and reading_exists:
                await flash(
                    "Такое чтение уже существует, редактировать надо по ссылке из него"
                )
            elif same_reading:
                # Обновление существующей строки + правка сообщения в TG.
                await grist_manager.patch_data(
                    MTLGrist.QUESTION_DATA,
                    {
                        "records": [
                            {
                                "id": data_row["id"],
                                "fields": {
                                    "BODY": inquiry,
                                    "STATUS": status,
                                },
                            }
                        ]
                    },
                )
                if question.get("TITLE") != short_subject:
                    await grist_manager.patch_data(
                        MTLGrist.QUESTIONS,
                        {
                            "records": [
                                {
                                    "id": question["id"],
                                    "fields": {
                                        "TITLE": short_subject,
                                    },
                                }
                            ]
                        },
                    )
                await grist_manager.patch_data(
                    MTLGrist.QUESTIONS,
                    {
                        "records": [
                            {
                                "id": question["id"],
                                "fields": {
                                    "READING": new_reading,
                                },
                            }
                        ]
                    },
                )
                text = get_full_text(
                    status, inquiry, links_url, question_uuid, username
                )
                try:
                    await skynet_bot.edit_message_text(
                        chat_id=int(f"-100{chat_ids[new_reading]}"),
                        text=text,
                        parse_mode=SULGUK_PARSE_MODE,
                        disable_web_page_preview=True,
                        message_id=data_row["TELEGRAM_LINK"].split("/")[-1],
                    )
                except Exception as e:
                    logger.info(f"Error with telegram publishing: {e}")
                    await flash("Вопрос сохранён, но правка в Telegram не прошла.")
                await flash("Вопрос успешно обновлён.", "good")
                return redirect(f"/d2/{question_uuid}")
            else:
                # Смена чтения: новая строка QUESTION_DATA + новое сообщение.
                new_uuid = uuid.uuid4().hex
                text = get_full_text(status, inquiry, links_url, new_uuid, username)
                try:
                    msg = await skynet_bot.send_message(
                        chat_id=int(f"-100{chat_ids[new_reading]}"),
                        text=text,
                        parse_mode=SULGUK_PARSE_MODE,
                        disable_web_page_preview=True,
                    )
                    message_id = msg.message_id
                except Exception as e:
                    logger.info(f"Error with telegram publishing: {e}")
                    message_id = None

                fields = {
                    "QUESTION_ID": question["id"],
                    "READING": new_reading,
                    "UUID": new_uuid,
                    "BODY": inquiry,
                    "EXTRA": "",
                    "STATUS": status,
                    "CREATED_BY": username,
                    "CREATED_AT": datetime.now().isoformat(),
                }
                if message_id is not None:
                    fields["TELEGRAM_LINK"] = (
                        f"https://t.me/c/{chat_ids[new_reading]}/{message_id}"
                    )
                await grist_manager.post_data(
                    MTLGrist.QUESTION_DATA, {"records": [{"fields": fields}]}
                )
                if question.get("TITLE") != short_subject:
                    await grist_manager.patch_data(
                        MTLGrist.QUESTIONS,
                        {
                            "records": [
                                {
                                    "id": question["id"],
                                    "fields": {
                                        "TITLE": short_subject,
                                    },
                                }
                            ]
                        },
                    )
                await grist_manager.patch_data(
                    MTLGrist.QUESTIONS,
                    {
                        "records": [
                            {
                                "id": question["id"],
                                "fields": {
                                    "READING": new_reading,
                                },
                            }
                        ]
                    },
                )
                if message_id is None:
                    await flash("Чтение создано, но публикация в Telegram не прошла.")
                await flash("Вопрос успешно обновлён.", "good")
                return redirect(f"/d2/{new_uuid}")

    statuses_list = [
        (status_, "selected" if status_ == status else "") for status_ in statuses
    ]
    readings_total = sum(
        1 for row in question_data if row.get("QUESTION_ID") == question["id"]
    )
    return await render_template(
        "d2_question.html",
        question_number=question_number,
        row_uuid=question_uuid,
        statuses=statuses_list,
        user_weight=user_weight,
        short_subject=short_subject,
        inquiry=inquiry,
        reading=reading,
        readings_total=readings_total,
        links_url=links_url,
        fragment_mode=request.headers.get("HX-Request") == "true",
    )


@blueprint.route("/d2/fragment/form", methods=("GET",))
async def cmd_d2_form():
    template_id = request.args.get("template_id", type=int)

    template_title, inquiry = (
        "",
        (
            "<br>"
            "<b>Предложение:</b> <br><br>"
            "<b>Обоснование:</b> <br><br>"
            "<b>Примечание:</b> <br><br>"
            "<b>Имплементация:</b> <br><br>"
        ),
    )
    if template_id is not None:
        _, _, templates = await _load_question_tables()
        template = next((t for t in templates if t.get("id") == template_id), None)
        if template:
            template_title = template.get("TITLE") or ""
            inquiry = template.get("BODY") or ""

    user_weight = await check_user_weight(False)
    statuses_list = [(status_, "") for status_ in statuses]

    from other.grist_tools import grist_manager, MTLGrist

    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    numbers = [q.get("NUMBER") for q in questions if q.get("NUMBER") is not None]
    next_number = max(numbers, default=0) + 1

    return await render_template(
        "d2_form.html",
        question_number=next_number,
        short_subject="",
        inquiry=inquiry,
        template_title=template_title,
        reading=1,
        statuses=statuses_list,
        user_weight=user_weight,
        fragment_mode=request.headers.get("HX-Request") == "true",
    )


@blueprint.route("/d2/number", methods=("GET",))
async def cmd_d2_get_number():
    from other.grist_tools import grist_manager, MTLGrist

    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    numbers = [q.get("NUMBER") for q in questions if q.get("NUMBER") is not None]
    return jsonify({"number": str(max(numbers, default=0) + 1)})


@blueprint.route("/d2/add", methods=("POST",))
async def cmd_d2_add():
    session["return_to"] = request.url

    user_weight = await check_user_weight(False)
    form_data = await request.form
    question_number = form_data["question_number"]
    short_subject = form_data["short_subject"]
    inquiry = form_data["inquiry"]
    status = form_data["status"]
    reading = int(form_data["reading"])

    user_weight = await check_user_weight()
    if user_weight <= 0:
        return redirect("/d2")

    from other.grist_tools import grist_manager, MTLGrist

    questions, question_data, _ = await _load_question_tables()
    if any(str(q.get("NUMBER")) == str(question_number) for q in questions):
        existing = next(
            (
                r
                for r in question_data
                if r.get("QUESTION_ID")
                == next(
                    q["id"]
                    for q in questions
                    if str(q.get("NUMBER")) == str(question_number)
                )
            ),
            None,
        )
        link = f"/d2/{existing['UUID']}" if existing else "/d2"
        await flash(
            f"Вопрос с номером {question_number} уже существует. "
            f'<a href="{link}">Редактировать существующий вопрос</a> '
            f"или создайте новый с другим номером."
        )
        return redirect("/d2/fragment/form")

    d_uuid = uuid.uuid4().hex
    username = "@" + session["userdata"]["username"]

    # 1. Строка в QUESTIONS.
    await grist_manager.post_data(
        MTLGrist.QUESTIONS,
        {
            "records": [
                {
                    "fields": {
                        "NUMBER": int(question_number),
                        "TITLE": short_subject,
                        "READING": reading,
                    }
                }
            ]
        },
    )
    questions, _, _ = await _load_question_tables()
    question_id = next(
        q["id"] for q in questions if str(q.get("NUMBER")) == str(question_number)
    )

    # 2. Сообщение в Telegram.
    text = get_full_text(status, inquiry, [[], [], []], d_uuid, username)
    try:
        msg = await skynet_bot.send_message(
            chat_id=int(f"-100{chat_ids[reading]}"),
            text=text,
            parse_mode=SULGUK_PARSE_MODE,
            disable_web_page_preview=True,
        )
        message_id = msg.message_id
    except Exception as e:
        logger.info(f"Error with telegram publishing: {e}")
        message_id = None

    fields = {
        "QUESTION_ID": question_id,
        "READING": reading,
        "UUID": d_uuid,
        "BODY": inquiry,
        "EXTRA": "",
        "STATUS": status,
        "CREATED_BY": username,
        "CREATED_AT": datetime.now().isoformat(),
    }
    if message_id is not None:
        fields["TELEGRAM_LINK"] = f"https://t.me/c/{chat_ids[reading]}/{message_id}"
    # 3. Строка в QUESTION_DATA.
    await grist_manager.post_data(
        MTLGrist.QUESTION_DATA, {"records": [{"fields": fields}]}
    )

    if message_id is None:
        await flash("Error with telegram publishing")
    else:
        await flash("Вопрос успешно добавлен.", "good")
    return redirect(f"/d2/{d_uuid}")


@blueprint.route("/d2/copy", methods=("GET",))
async def cmd_d2_copy():
    data_row, question = await _find_question_row(request.args.get("uuid", ""))
    if data_row is None or question is None:
        return "Decision not exist =("

    user_weight = await check_user_weight(False)
    statuses_list = [(status_, "") for status_ in statuses]

    from other.grist_tools import grist_manager, MTLGrist

    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    numbers = [q.get("NUMBER") for q in questions if q.get("NUMBER") is not None]
    next_number = max(numbers, default=0) + 1

    return await render_template(
        "d2_form.html",
        question_number=next_number,
        short_subject=(question.get("TITLE") or "") + " (копия)",
        inquiry=data_row.get("BODY") or "",
        template_title=f"Копия вопроса №{question.get('NUMBER')}",
        reading=1,
        statuses=statuses_list,
        user_weight=user_weight,
        fragment_mode=request.headers.get("HX-Request") == "true",
    )


@blueprint.route("/d2/template/from", methods=("POST",))
async def cmd_d2_template_from():
    form_data = await request.form
    template_uuid = form_data.get("uuid", "")
    title = (form_data.get("title") or "").strip()

    data_row, question = await _find_question_row(template_uuid)
    if data_row is None or question is None:
        return "Decision not exist =("

    from other.grist_tools import grist_manager, MTLGrist

    await grist_manager.post_data(
        MTLGrist.QUESTION_TEMPLATES,
        {
            "records": [
                {
                    "fields": {
                        "TITLE": title or (question.get("TITLE") or ""),
                        "BODY": data_row.get("BODY") or "",
                    }
                }
            ]
        },
    )
    await flash("Шаблон сохранён.", "good")
    return redirect(f"/d2/{template_uuid}")


@blueprint.route("/d2/fragment/edit", methods=("GET",))
async def cmd_d2_edit():
    from other.grist_tools import grist_manager, MTLGrist

    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    question_data = await grist_manager.load_table_data(MTLGrist.QUESTION_DATA) or []

    data_by_question = {}
    for row in question_data:
        question_id = row.get("QUESTION_ID")
        reading = row.get("READING")
        if question_id is None or reading is None:
            continue
        try:
            reading_int = int(reading)
        except (TypeError, ValueError):
            continue
        data_by_question.setdefault(question_id, []).append(
            {
                "reading": reading_int,
                "status": row.get("STATUS") or "",
                "uuid": row.get("UUID") or "",
            }
        )

    items = []
    for question in questions:
        number = question.get("NUMBER")
        title = question.get("TITLE") or ""
        question_id = question.get("id")
        readings = data_by_question.get(question_id, [])
        max_reading = max((r["reading"] for r in readings), default=0)
        status = ""
        for r in readings:
            if r["reading"] == max_reading:
                status = r["status"]
                break
        items.append(
            {
                "number": number,
                "title": title,
                "reading": max_reading,
                "status": status,
                "readings_count": len(readings),
                "uuids": [r["uuid"] for r in data_by_question.get(question_id, [])],
                "first_uuid": data_by_question.get(question_id, [{}])[0].get(
                    "uuid", ""
                ),
            }
        )

    items.sort(key=lambda row: (row["number"] is None, row["number"]), reverse=True)

    status_param = request.args.get("status")
    if status_param in (None, "", "active"):
        filtered = [row for row in items if row["status"] in D2_ACTIVE_STATUSES]
    elif status_param == "all":
        filtered = items
    elif status_param in statuses:
        filtered = [row for row in items if row["status"] == status_param]
    else:
        filtered = items

    query = (request.args.get("q") or "").strip().lower()
    if query:
        filtered = [
            row
            for row in filtered
            if query in str(row["title"]).lower()
            or query in str(row["number"]).lower()
        ]

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", D2_PAGE_SIZE))
    except (TypeError, ValueError):
        per_page = D2_PAGE_SIZE
    per_page = min(max(per_page, 1), 500)
    total_pages = max((len(filtered) + per_page - 1) // per_page, 1)
    page = min(page, total_pages)
    page_items = filtered[(page - 1) * per_page : page * per_page]

    return await render_template(
        "d2_frag_edit.html",
        items=page_items,
        current_uuid=request.args.get("uuid"),
        page=page,
        total_pages=total_pages,
        total_items=len(filtered),
        status_filter=status_param or "active",
        query=query,
        statuses=statuses,
    )


@blueprint.route("/d2/fragment/new", methods=("GET",))
async def cmd_d2_new():
    from other.grist_tools import grist_manager, MTLGrist

    templates = await grist_manager.load_table_data(MTLGrist.QUESTION_TEMPLATES) or []
    items = []
    for template in templates:
        items.append(
            {
                "id": template.get("id"),
                "title": template.get("TITLE") or "",
                "body": template.get("BODY") or "",
            }
        )

    items.sort(key=lambda row: row["title"].lower())
    return await render_template("d2_frag_new.html", templates=items)


@blueprint.route("/d/<decision_id>", methods=("GET", "POST"))
async def cmd_show_decision(decision_id):
    session["return_to"] = request.url
    if len(decision_id) != 32:
        abort(404)

    async with current_app.db_pool() as db_session:
        result = await db_session.execute(
            select(Decisions).filter(Decisions.uuid == decision_id)
        )
        decision = result.scalars().first()
        if decision:
            res1 = await db_session.execute(
                select(Decisions.url).filter(
                    Decisions.num == decision.num, Decisions.reading == 1
                )
            )
            res2 = await db_session.execute(
                select(Decisions.url).filter(
                    Decisions.num == decision.num, Decisions.reading == 2
                )
            )
            res3 = await db_session.execute(
                select(Decisions.url).filter(
                    Decisions.num == decision.num, Decisions.reading == 3
                )
            )
            links_url = (res1.first(), res2.first(), res3.first())
            result = (decision, links_url)
        else:
            result = None
    if not result:
        return "Decision not exist =("

    decision, links_url = result
    question_number, short_subject, inquiry, reading = (
        decision.num,
        decision.description,
        decision.full_text,
        decision.reading,
    )
    status = decision.status

    user_weight = await check_user_weight(False)
    if request.method == "POST":
        user_weight = await check_user_weight()
        if user_weight > 0:
            form_data = await request.form
            question_number = decision.num
            short_subject = form_data["short_subject"]
            inquiry = form_data["inquiry"]
            reading = int(form_data["reading"])
            username = "@" + session["userdata"]["username"]
            status = form_data["status"]

            # new or update
            # если не меняем чтение то обновление
            if reading == decision.reading:
                async with current_app.db_pool() as db_session:
                    result = await db_session.execute(
                        select(Decisions).filter(Decisions.uuid == decision_id)
                    )
                    dec = result.scalars().first()
                    dec.full_text = inquiry
                    dec.status = status
                    await db_session.commit()
                text = get_full_text(
                    status, inquiry, links_url, decision.uuid, decision.username
                )
                await skynet_bot.edit_message_text(
                    chat_id=int(f"-100{chat_ids[reading]}"),
                    text=text,
                    parse_mode=SULGUK_PARSE_MODE,
                    disable_web_page_preview=True,
                    message_id=decision.url.split("/")[-1],
                )

            # если сменили чтение,
            if reading != decision.reading:
                # но оно есть, то ругаемся.
                if links_url[reading - 1] is not None:
                    await flash(
                        "Такое чтение уже существует, редактировать надо по ссылке из него"
                    )
                else:
                    new_uuid = uuid.uuid4().hex

                    text = get_full_text(status, inquiry, links_url, new_uuid, username)
                    try:
                        msg = await skynet_bot.send_message(
                            chat_id=int(f"-100{chat_ids[reading]}"),
                            text=text,
                            parse_mode=SULGUK_PARSE_MODE,
                            disable_web_page_preview=True,
                        )
                        message_id = msg.message_id
                    except Exception as e:
                        logger.info(f"Error with telegram publishing: {e}")
                        message_id = None

                    if message_id is None:
                        await flash("Error with telegram publishing")
                    else:
                        url = f"https://t.me/c/{chat_ids[reading]}/{message_id}"

                        async with current_app.db_pool() as db_session:
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
                            await db_session.commit()

                        # Nmbr	Name	Text	Author	First	Second	Vote	Sign	Decision
                        # 1     2       3       4       5       6       7       8       9
                        if reading == 2:
                            await gs_update_decision(decision.num, 6, url)
                        if reading == 3:
                            await gs_update_decision(decision.num, 8, url)

                        return redirect(f"/d/{new_uuid}")

    statuses_list = [
        (status_, "selected" if status_ == status else "") for status_ in statuses
    ]

    return await render_template(
        "tabler_decision.html",
        question_number=question_number,
        statuses=statuses_list,
        user_weight=user_weight,
        short_subject=short_subject,
        inquiry=inquiry,
        reading=reading,
        links_url=links_url,
    )


@blueprint.route("/decision/number", methods=("GET", "POST"))
async def cmd_get_number_decision():
    number = await gs_get_last_id()
    return jsonify({"number": str(number[0] + 1)})


@blueprint.route("/decision/update_text", methods=["POST"])
async def update_decision_text():
    if request.method == "POST":
        # Проверка API ключа
        api_key = request.headers.get("Authorization")
        if api_key != f"Bearer {config.eurmtl_key.get_secret_value()}":
            return jsonify({"message": "Unauthorized"}), 401

        # Получение данных из запроса
        data = await request.get_json()
        msg_url = data.get("msg_url")
        msg_text = data.get("msg_text")

        if not msg_url or not msg_text:
            return jsonify({"message": "Missing data"}), 400

        # Обновление текста в базе данных
        async with current_app.db_pool() as db_session:
            result = await db_session.execute(
                select(Decisions).filter(Decisions.url == msg_url)
            )
            decision = result.scalars().first()
            if decision is not None:
                decision.full_text = msg_text
                await db_session.commit()
                updated = True
            else:
                updated = False
        if updated:
            return jsonify({"message": "Text updated successfully"}), 200
        else:
            return jsonify({"message": "Decision not found"}), 404


async def migrate_decisions_to_grist():
    async with current_app.db_pool() as db_session:
        result = await db_session.execute(
            select(Decisions).order_by(Decisions.num, Decisions.reading, Decisions.dt)
        )
        decisions = result.scalars().all()
    if not decisions:
        logger.info("No decisions found for migration.")
        return

    from other.grist_tools import grist_manager, MTLGrist

    users = await grist_manager.load_table_data(MTLGrist.SP_USERS) or []
    username_to_id = {}
    for user in users:
        username = (user.get("USERNAME") or "").lstrip("@").lower()
        if username:
            username_to_id[username] = user["id"]

    existing_questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    number_to_question_id = {}
    question_id_to_number = {}
    for question in existing_questions:
        number = question.get("NUMBER")
        if number is None:
            continue
        number_to_question_id[number] = question["id"]
        question_id_to_number[question["id"]] = number

    existing_question_data = (
        await grist_manager.load_table_data(MTLGrist.QUESTION_DATA) or []
    )
    existing_pairs = set()
    for data in existing_question_data:
        question_id = data.get("QUESTION_ID")
        reading = data.get("READING")
        if question_id is None or reading is None:
            continue
        number = question_id_to_number.get(question_id)
        if number is not None:
            existing_pairs.add((number, int(reading)))

    dedup = {}
    max_reading = {}
    for decision in decisions:
        key = (decision.num, decision.reading)
        if key not in dedup:
            dedup[key] = decision
        max_reading[decision.num] = max(
            decision.reading, max_reading.get(decision.num, 0)
        )

    questions_to_create = []
    for number, reading in max_reading.items():
        if number in number_to_question_id:
            continue
        decision = dedup.get((number, reading)) or dedup.get((number, 1))
        title = decision.description if decision else ""
        questions_to_create.append(
            {
                "fields": {
                    "NUMBER": number,
                    "TITLE": title,
                    "READING": reading,
                }
            }
        )

    if questions_to_create:
        await grist_manager.post_data(
            MTLGrist.QUESTIONS, {"records": questions_to_create}
        )
        existing_questions = (
            await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
        )
        number_to_question_id = {
            q.get("NUMBER"): q["id"]
            for q in existing_questions
            if q.get("NUMBER") is not None
        }

    question_data_to_create = []
    for (number, reading), decision in dedup.items():
        if (number, reading) in existing_pairs:
            continue

        question_id = number_to_question_id.get(number)
        if question_id is None:
            continue

        fields = {
            "QUESTION_ID": question_id,
            "READING": reading,
            "UUID": decision.uuid,
            "TELEGRAM_LINK": decision.url,
            "BODY": decision.full_text or "",
            "EXTRA": "",
            "STATUS": decision.status or "",
        }

        if decision.dt:
            fields["CREATED_AT"] = decision.dt.isoformat()

        username = (decision.username or "").lstrip("@").lower()
        created_by_id = username_to_id.get(username)
        if created_by_id is not None:
            fields["CREATED_BY"] = created_by_id

        question_data_to_create.append({"fields": fields})

    if question_data_to_create:
        batch_size = 200
        for i in range(0, len(question_data_to_create), batch_size):
            batch = question_data_to_create[i : i + batch_size]
            await grist_manager.post_data(MTLGrist.QUESTION_DATA, {"records": batch})
        logger.info(
            "Migration completed: %s question rows, %s question_data rows.",
            len(questions_to_create),
            len(question_data_to_create),
        )
    else:
        logger.info("No new QUESTION_DATA rows to migrate.")


if __name__ == "__main__":
    asyncio.run(migrate_decisions_to_grist())
