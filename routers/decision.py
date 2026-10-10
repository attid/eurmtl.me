import asyncio
import uuid
from datetime import datetime

from loguru import logger
from quart import (
    Blueprint,
    request,
    render_template,
    flash,
    jsonify,
    session,
    redirect,
    abort,
    Response,
)
from sulguk import SULGUK_PARSE_MODE

import urllib.parse

from other.config_reader import config
from other.cache_tools import AsyncTTLCache
from services.rich_converter import html_to_rich_message
from other.telegram_tools import skynet_bot
from other.grist_tools import DEFAULT_ORG_NAME

blueprint = Blueprint("decision", __name__)


def _d2_base_url() -> str:
    """Origin сайта для абсолютных URL картинок в rich-посте
    (Telegram скачивает /d2/img/<id> сам): request.host текущего запроса."""
    scheme = request.scheme if request else "https"
    host = request.host if request else "eurmtl.me"
    return f"{scheme}://{host}"


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


secretary_ids_cache = AsyncTTLCache(ttl_seconds=60)  # Предвыборка секретарей


async def _secretaries_by_account() -> dict[str, set[int]]:
    """Секретари по счетам: {адрес счёта: {telegram_id}}.

    В проде берём get_secretaries() (grist_cache), в тест-режиме кеш не
    инициализируется — читаем таблицы EURMTL_secretaries/accounts/users
    напрямую через grist_manager. Результат кешируется на минуту:
    секретарские проверки зовутся несколько раз за запрос.
    """
    from other.grist_tools import get_secretaries, grist_manager, MTLGrist

    cached = await secretary_ids_cache.get("by_account")
    if cached is not None:
        return cached

    if not config.test_mode:
        secretaries = await get_secretaries()
        by_account: dict[str, set[int]] = {
            account: {int(tg) for tg in ids} for account, ids in secretaries.items()
        }
    else:
        secretary_rows = (
            await grist_manager.load_table_data(MTLGrist.EURMTL_secretaries) or []
        )
        account_rows = (
            await grist_manager.load_table_data(MTLGrist.EURMTL_accounts) or []
        )
        user_rows = await grist_manager.load_table_data(MTLGrist.EURMTL_users) or []

        account_by_id = {a["id"]: a.get("account") for a in account_rows if a.get("id")}
        user_tg_by_id = {
            u["id"]: u.get("telegram_id") for u in user_rows if u.get("id")
        }
        by_account = {}
        for record in secretary_rows:
            account = account_by_id.get(record.get("account"))
            if not account:
                continue
            telegram_ids = by_account.setdefault(account, set())
            for user_id in record.get("users") or []:
                tg_id = user_tg_by_id.get(user_id)
                if tg_id:
                    telegram_ids.add(int(tg_id))

    await secretary_ids_cache.set("by_account", by_account)
    return by_account


async def _org_secretary_addresses(org: str) -> set[int]:
    """Telegram_id секретарей счёта MAIN_ADDRESS организации org."""
    from other import orgs_config

    main_address = next(
        (o.main_address for o in orgs_config.ORGS if o.name == org), None
    )
    if not main_address:
        return set()
    by_account = await _secretaries_by_account()
    return by_account.get(main_address, set())


def _org_readings(org: str) -> int:
    """Число чтений орги (0 = чтений нет, один вопрос-пост)."""
    from other import orgs_config

    return next((o.readings for o in orgs_config.ORGS if o.name == org), 0)


async def _is_org_secretary(org: str) -> bool:
    """Текущий пользователь (по userdata.id) — секретарь счёта MAIN_ADDRESS орги."""
    user_id = (session.get("userdata") or {}).get("id")
    if user_id in (None, ""):
        return False
    return int(user_id) in await _org_secretary_addresses(org)


async def _d2_edit_allowed(org: str) -> bool:
    """Гейт правок d2 (решение владельца): секретарь орги ИЛИ подписант
    её MAIN_ADDRESS."""
    if not org:
        return False
    if await _is_org_secretary(org):
        return True
    user_telegram_id = await _session_user_telegram_id()
    if user_telegram_id is None:
        return False
    from other.grist_tools import user_org_names

    return org in await user_org_names(user_telegram_id)


async def _session_user_telegram_id() -> int | None:
    """Telegram_id текущего пользователя из сессии (userdata.id)."""
    userdata = session.get("userdata") or {}
    user_id = userdata.get("id")
    if user_id in (None, ""):
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


async def _user_visible_orgs() -> set:
    """Организации, видимые текущему пользователю.

    Видимость = подписант MAIN_ADDRESS (user_org_names) ИЛИ секретарь счёта
    этой орги (EURMTL_secretaries на MAIN_ADDRESS). Секретарство одной орги
    само по себе другие орги не открывает (решение владельца, 2026-10-09).
    Неопознанный пользователь не видит ничего.
    """
    from other import orgs_config
    from other.grist_tools import user_org_names

    user_telegram_id = await _session_user_telegram_id()
    if user_telegram_id is None:
        return set()

    visible = await user_org_names(user_telegram_id)

    for org in orgs_config.ORGS:
        if org.name in visible or not org.main_address:
            continue
        if user_telegram_id in await _org_secretary_addresses(org.name):
            visible.add(org.name)
    return visible


async def _org_visible(org_name: str) -> bool:
    """Видна ли организация текущему пользователю."""
    if not org_name:
        return False
    visible_orgs = await _user_visible_orgs()
    return org_name in visible_orgs


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


async def resolve_channel(org_name: str | None, reading: int) -> str | None:
    """Канал публикации чтения N: из orgs_config, fallback — хардкод фонда."""
    from other.grist_tools import resolve_org_channel

    channel = resolve_org_channel(org_name, reading)
    if channel is not None:
        return channel
    if 1 <= reading <= 3:
        return str(chat_ids[reading])
    return None


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


D2_RICH_ENABLED = True  # kill-switch пилота rich-постов


_READING_TAG = {1: "first_reading", 2: "second_reading", 3: "third_reading"}


def _d2_rich_blocks(status: str, inquiry: str, org: str = "", reading: int = 1,
                    question_number=None, title: str = "",
                    links_url=([], [], []), uuid_url: str = "",
                    username: str = ""):
    """Блоки InputRichMessage. Формат зависит от org.hash_position:
    - suffix (PFM/USDMM/GORA): жирная строка статуса, затем тело, ссылки внизу.
    - prefix (MTLA): первая строка "<статус> #<N>_reading", затем "Вопрос N:
      <тема>" и тело (формат канала MTLA Council, решение владельца 2026-10-10).
    Внизу всегда подвал как в legacy: ссылки на чтения, Edit on eurmtl.me,
    Added by. None — конвертация не удалась (фолбэк sendMessage+SULGUK)."""
    if not D2_RICH_ENABLED:
        return None
    from other import orgs_config

    org_obj = next((o for o in orgs_config.ORGS if o.name == org), None)
    if org_obj and org_obj.hash_position == "prefix":
        tag = _READING_TAG.get(reading, f"{reading}_reading")
        num = f"Вопрос {question_number}: " if question_number else ""
        html = f"<p><b>{status} #{tag}</b></p><p><b>{num}{title}</b>{inquiry}</p>"
    else:
        html = f"<p><b>{status}</b></p>{inquiry}"
    html += "<p>---</p>"
    for label, link in zip(
        ("Первое чтение", "Второе чтение", "Третье чтение"), links_url
    ):
        if link:
            html += f'<p><a href="{link[0]}">{label}</a></p>'
    html += "<p>-</p>"
    if uuid_url:
        # /d/<uuid> — целевой URL навсегда: после cutover'а (вырезание d1)
        # этот роут станет d2-механизмом, посты править не придётся.
        html += f'<p><a href="{_d2_base_url()}/d/{uuid_url}">Edit on eurmtl.me</a></p>'
    if username:
        html += f"<p>Added by {username}</p>"
    try:
        blocks = html_to_rich_message(html, _d2_base_url())["blocks"]
    except Exception as e:
        logger.warning(f"D2 rich convert failed, fallback to sulguk: {e}")
        return None
    if not blocks:
        logger.warning("D2 rich convert produced no blocks, fallback to sulguk")
        return None
    return blocks


async def _d2_send_rich(channel: str, status: str, inquiry: str,
                        org: str = "", reading: int = 1,
                        question_number=None, title: str = "",
                        links_url=([], [], []), uuid_url: str = "",
                        username: str = ""):
    """sendRichMessage в канал. Возвращает message_id или None (ошибка уже
    залогирована warning'ом — вызывающий решает про фолбэк)."""
    blocks = _d2_rich_blocks(status, inquiry, org, reading, question_number,
                             title, links_url=links_url, uuid_url=uuid_url,
                             username=username)
    if blocks is None:
        return None
    try:
        msg = await skynet_bot.send_rich_message(
            chat_id=int(f"-100{channel}"),
            rich_message={"blocks": blocks},
        )
        logger.info(
            f"D2 TG rich OK: chat=-100{channel} message_id={msg.message_id} "
            f"[{org}] №{question_number} r{reading} status={status!r}"
        )
        return msg.message_id
    except Exception as e:
        logger.warning(
            f"D2 TG rich FAIL: chat=-100{channel} [{org}] №{question_number} "
            f"r{reading}: {e}"
        )
        return None


async def _d2_edit_rich(channel: str, message_id, status: str, inquiry: str,
                        org: str = "", reading: int = 1,
                        question_number=None, title: str = "",
                        links_url=([], [], []), uuid_url: str = "",
                        username: str = "") -> bool:
    """editMessageText(rich_message=...) опубликованного поста. message_id
    передаётся строкой как есть (из TELEGRAM_LINK), приводим к int.
    False — не получилось (включая «старый пост был не rich»): вызывающий
    републикует или падает в фолбэк."""
    blocks = _d2_rich_blocks(status, inquiry, org, reading, question_number,
                             title, links_url=links_url, uuid_url=uuid_url,
                             username=username)
    if blocks is None:
        return False
    try:
        await skynet_bot.edit_message_text(
            chat_id=int(f"-100{channel}"),
            message_id=int(message_id),
            rich_message={"blocks": blocks},
        )
        logger.info(
            f"D2 TG edit OK: chat=-100{channel} message_id={message_id} "
            f"[{org}] №{question_number} r{reading}"
        )
        return True
    except Exception as e:
        logger.warning(
            f"D2 TG edit FAIL: chat=-100{channel} message_id={message_id} "
            f"[{org}] №{question_number} r{reading}: {e}"
        )
        return False


async def _d2_send_legacy(channel: str, text: str):
    """Старый путь: sendMessage + SULGUK. Возвращает message_id или None."""
    try:
        msg = await skynet_bot.send_message(
            chat_id=int(f"-100{channel}"),
            text=text,
            parse_mode=SULGUK_PARSE_MODE,
            disable_web_page_preview=True,
        )
        logger.info(f"D2 TG legacy OK: chat=-100{channel} message_id={msg.message_id}")
        return msg.message_id
    except Exception as e:
        logger.warning(f"D2 TG legacy FAIL: chat=-100{channel}: {e}")
        return None


@blueprint.route("/decision", methods=("GET", "POST"))
@blueprint.route("/d", methods=("GET", "POST"))
async def cmd_add_decision():
    """Cutover (решение владельца 2026-10-11): создание вопроса — d2.
    GET: на фрагмент-форму d2 (воркспейс выберет/сохранится). POST: старая
    d1-форма больше не поддерживается — на фрагмент-форму."""
    return redirect("/d2/fragment/new")


def _org_next_number(questions: list, org: str) -> int:
    """Следующий номер вопроса: max(NUMBER)+1 внутри орги (per-org нумерация
    с 1 — решение владельца 2026-10-09), номера разных орг независимы."""
    numbers = [
        q.get("NUMBER")
        for q in questions
        if (q.get("ORG") or DEFAULT_ORG_NAME) == org and q.get("NUMBER") is not None
    ]
    return max(numbers, default=0) + 1


@blueprint.route("/d2", methods=("GET",), strict_slashes=False)
async def cmd_d2_index():
    session_org = await _d2_session_org()
    if session_org:
        return redirect("/d2/fragment/edit?status=active")

    visible = await _user_visible_orgs()
    return await render_template(
        "d2_workspace.html",
        org_names=sorted(visible),
        no_orgs=not visible,
    )


async def _d2_session_org() -> str | None:
    """Текущий воркспейс из сессии; None, если не выбран или невалиден."""
    org = (session.get("d2_org") or "").strip()
    if org and await _org_visible(org):
        return org
    return None


async def _d2_workspace_context() -> dict:
    """render-контекст шапки: текущая орга + видимые для переключателя."""
    return {
        "org": await _d2_session_org(),
        "org_names": await _org_names(),
    }


@blueprint.route("/d2/workspace", methods=("POST",))
async def cmd_d2_workspace():
    form_data = await request.form
    org = (form_data.get("org") or "").strip()
    if await _org_visible(org):
        session["d2_org"] = org
        return redirect("/d2/fragment/edit?status=active")
    await flash("Такая организация вам недоступна.")
    return redirect("/d2")


question_tables_cache = AsyncTTLCache(ttl_seconds=5)


async def _load_question_tables():
    """Возвращает (questions, question_data, templates) из Grist.

    Кеш 5 секунд: один пользовательский проход (список → вопрос → сохранение)
    не дёргает Grist по несколько раз. После записи сбрасывается
    (_d2_invalidate_cache), свои правки видны сразу.
    """
    cached = await question_tables_cache.get("tables")
    if cached is not None:
        return cached
    from other.grist_tools import grist_manager, MTLGrist

    tables = (
        await grist_manager.load_table_data(MTLGrist.QUESTIONS) or [],
        await grist_manager.load_table_data(MTLGrist.QUESTION_DATA) or [],
        await grist_manager.load_table_data(MTLGrist.QUESTION_TEMPLATES) or [],
    )
    await question_tables_cache.set("tables", tables)
    return tables


def _d2_invalidate_cache() -> None:
    """Сброс кеша после записи в D2_* таблицы."""
    question_tables_cache.cache.clear()


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


async def _org_names() -> list[str]:
    """Имена организаций, видимых текущему пользователю (для переключателя
    воркспейса в шапке)."""
    return sorted(await _user_visible_orgs())


@blueprint.route("/d2/<question_uuid>", methods=("GET", "POST"))
async def cmd_d2_show(question_uuid):
    session["return_to"] = request.url

    # Просмотр d2 только для авторизованных с доступом к орге вопроса:
    # аноним и чужак получают одинаковый отказ — существование не палить.
    if session.get("userdata") is None:
        return "Decision not exist =(", 404
    data_row, question = await _find_question_row(question_uuid)
    if data_row is None or question is None:
        return "Decision not exist =(", 404
    org = question.get("ORG") or DEFAULT_ORG_NAME
    if not await _org_visible(org):
        # Чужая организация — как несуществующая, существование не палить.
        return "Decision not exist =(", 404

    questions, question_data, _ = await _load_question_tables()
    links_url = _question_links(question["id"], question_data)
    # Все чтения вопроса для навигации на экране: [(reading, uuid), ...].
    readings_nav = sorted(
        (int(r.get("READING")), r.get("UUID") or "")
        for r in question_data
        if r.get("QUESTION_ID") == question["id"]
        and str(r.get("READING") or "").isdigit()
    )

    question_number = question.get("NUMBER")
    short_subject = question.get("TITLE") or ""
    inquiry = data_row.get("BODY") or ""
    reading = _readings_int(data_row) or 1
    status = data_row.get("STATUS") or ""
    username = data_row.get("CREATED_BY") or ""

    user_weight = 1 if await _d2_edit_allowed(org) else 0
    if request.method == "POST":
        if user_weight > 0:
            form_data = await request.form
            short_subject = form_data["short_subject"]
            inquiry = form_data["inquiry"]
            status = form_data["status"]
            new_reading = int(form_data.get("reading", reading))

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
                _d2_invalidate_cache()
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
                    _d2_invalidate_cache()
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
                _d2_invalidate_cache()
                text = get_full_text(
                    status, inquiry, links_url, question_uuid, username
                )
                telegram_link = data_row.get("TELEGRAM_LINK") or ""
                if not telegram_link:
                    # Черновик: Telegram не трогаем — публикация кнопкой
                    # «Опубликовать», править там нечего.
                    pass
                else:
                    channel = await resolve_channel(org, new_reading)
                    edited = False
                    if channel is not None:
                        edited = await _d2_edit_rich(
                            channel, telegram_link.split("/")[-1], status, inquiry,
                            org=org, reading=new_reading,
                            question_number=question.get("NUMBER"),
                            title=short_subject, links_url=links_url,
                            uuid_url=question_uuid, username=username,
                        )
                        if not edited:
                            # Пост мог быть не rich (старые публикации) —
                            # правим как раньше, обычным сообщением.
                            try:
                                await skynet_bot.edit_message_text(
                                    chat_id=int(f"-100{channel}"),
                                    text=text,
                                    parse_mode=SULGUK_PARSE_MODE,
                                    disable_web_page_preview=True,
                                    message_id=int(telegram_link.split("/")[-1]),
                                )
                                edited = True
                            except Exception as e:
                                logger.info(f"Error with telegram publishing: {e}")
                    if not edited:
                        await flash("Вопрос сохранён, но правка в Telegram не прошла.")
                await flash("Вопрос успешно обновлён.", "good")
                return redirect(f"/d2/{question_uuid}")
            else:
                # Смена чтения: сначала публикуем новое чтение (пост+ссылка),
                # потом правим пост прошлого (статус -> #next + ссылка на
                # новое чтение в подвале) — порядок определил владелец
                # 2026-10-10.
                new_uuid = uuid.uuid4().hex
                text = get_full_text(status, inquiry, links_url, new_uuid, username)
                channel = await resolve_channel(org, new_reading)
                message_id = None
                if channel is not None:
                    message_id = await _d2_send_rich(
                        channel, status, inquiry, org=org, reading=new_reading,
                        question_number=question.get("NUMBER"),
                        title=short_subject,
                    )
                    if message_id is None:
                        message_id = await _d2_send_legacy(channel, text)

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
                if message_id is not None and channel is not None:
                    fields["TELEGRAM_LINK"] = f"https://t.me/c/{channel}/{message_id}"
                await grist_manager.post_data(
                    MTLGrist.QUESTION_DATA, {"records": [{"fields": fields}]}
                )
                _d2_invalidate_cache()
                logger.info(
                    f"D2 reading change: новое чтение r={new_reading} "
                    f"uuid={new_uuid} QUESTION_ID={question['id']} [{org}] "
                    f"№{question.get('NUMBER')}, link={fields.get('TELEGRAM_LINK')!r}"
                )
                # Прошлое чтение (решение владельца 2026-10-10): в чтениях 1-2
                # #done не ставится никогда. ❗️ #active → ☑️ #next (работа по
                # нему окончена); 🔇 #canceled и 🔂 #resign не трогаем.
                # ✅ #done возможен только в финальном чтении и ставится
                # человеком вручную. Правим и Grist, и пост прошлого чтения:
                # сначала новое чтение опубликовано (выше), теперь его ссылка
                # известна — уходит в подвал правимого поста.
                if data_row.get("STATUS") == "❗️ #active":
                    await grist_manager.patch_data(
                        MTLGrist.QUESTION_DATA,
                        {
                            "records": [
                                {
                                    "id": data_row["id"],
                                    "fields": {"STATUS": "☑️ #next"},
                                }
                            ]
                        },
                    )
                    _d2_invalidate_cache()
                    logger.info(
                        f"D2 reading change: autostatus id={data_row['id']} "
                        f"[{org}] №{question.get('NUMBER')} ❗️ #active -> ☑️ #next"
                    )
                old_link = data_row.get("TELEGRAM_LINK") or ""
                if old_link and message_id is not None and channel is not None:
                    updated_links = list(links_url)
                    updated_links[new_reading - 1] = (
                        f"https://t.me/c/{channel}/{message_id}",
                    )
                    edited = await _d2_edit_rich(
                        await resolve_channel(org, reading),
                        old_link.split("/")[-1],
                        "☑️ #next",
                        data_row.get("BODY") or "",
                        org=org, reading=reading,
                        question_number=question.get("NUMBER"),
                        title=short_subject,
                        links_url=updated_links,
                        uuid_url=question_uuid, username=username,
                    )
                    logger.info(
                        f"D2 reading change: правка поста прошлого чтения "
                        f"r={reading} message_id={old_link.split('/')[-1]} -> "
                        f"☑️ #next, ok={edited}"
                    )
                    if not edited:
                        await flash(
                            "Чтение переключено, но статус в старом посте "
                            "Telegram обновить не удалось."
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
                    _d2_invalidate_cache()
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
                _d2_invalidate_cache()
                if message_id is None:
                    await flash("Чтение создано, но публикация в Telegram не прошла.")
                await flash("Вопрос успешно обновлён.", "good")
                return redirect(f"/d2/{new_uuid}")

    statuses_list = [
        (status_, "selected" if status_ == status else "") for status_ in statuses
    ]
    readings_total = _org_readings(org)
    is_draft = not (data_row.get("TELEGRAM_LINK") or "")
    can_publish = is_draft and await _is_org_secretary(org)
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
        readings_nav=readings_nav,
        links_url=links_url,
        can_publish=can_publish,
        **await _d2_workspace_context(),
    )


@blueprint.route("/d2/<question_uuid>/publish", methods=("POST",))
async def cmd_d2_publish(question_uuid):
    session["return_to"] = request.url

    data_row, question = await _find_question_row(question_uuid)
    if data_row is None or question is None:
        return "Decision not exist =(", 404
    org = question.get("ORG") or DEFAULT_ORG_NAME
    if not await _org_visible(org):
        return "Decision not exist =(", 404
    if not await _is_org_secretary(org):
        await flash("Публиковать могут только секретари.")
        return redirect(f"/d2/{question_uuid}")

    from other.grist_tools import grist_manager, MTLGrist

    questions, question_data, _ = await _load_question_tables()
    links_url = _question_links(question["id"], question_data)
    status = data_row.get("STATUS") or ""
    inquiry = data_row.get("BODY") or ""
    reading = _readings_int(data_row) or 1
    username = data_row.get("CREATED_BY") or ""

    telegram_link = data_row.get("TELEGRAM_LINK") or ""
    channel = await resolve_channel(org, reading)
    logger.info(
        f"D2 publish: uuid={question_uuid} [{org}] №{question.get('NUMBER')} "
        f"r{reading} channel={channel} old_link={telegram_link!r} "
        f"status={status!r} by={username or '?'}"
    )
    published = False
    if telegram_link and channel is not None:
        # Републикация: сначала пробуем поправить существующий пост rich'ем.
        # Не вышло (пост мёртв или был не rich) — уходим на ветку публикации
        # ниже.
        published = await _d2_edit_rich(
            channel, telegram_link.split("/")[-1], status, inquiry,
            org=org, reading=reading, question_number=question.get("NUMBER"),
            title=question.get("TITLE") or "", links_url=links_url,
            uuid_url=question_uuid, username=username,
        )
        if published:
            await flash("Пост в Telegram обновлён.", "good")

    if not published and channel is not None:
        # Публикация (в т.ч. републикация мёртвого/не-rich поста).
        message_id = await _d2_send_rich(
            channel, status, inquiry, org=org, reading=reading,
            question_number=question.get("NUMBER"),
            title=question.get("TITLE") or "", links_url=links_url,
            uuid_url=question_uuid, username=username,
        )
        if message_id is None:
            text = get_full_text(status, inquiry, links_url, question_uuid, username)
            message_id = await _d2_send_legacy(channel, text)
        if message_id is None:
            await flash("Публикация в Telegram не прошла.")
            return redirect(f"/d2/{question_uuid}")
        new_link = f"https://t.me/c/{channel}/{message_id}"
        if new_link != telegram_link:
            await grist_manager.patch_data(
                MTLGrist.QUESTION_DATA,
                {
                    "records": [
                        {"id": data_row["id"], "fields": {"TELEGRAM_LINK": new_link}}
                    ]
                },
            )
            _d2_invalidate_cache()
            logger.info(
                f"D2 publish: TELEGRAM_LINK обновлён id={data_row['id']}: "
                f"{telegram_link!r} -> {new_link!r}"
            )
        if telegram_link:
            await flash("Пост был удалён в Telegram — опубликован заново.", "good")
        else:
            await flash("Вопрос опубликован в Telegram.", "good")

    return redirect(f"/d2/{question_uuid}")


@blueprint.route("/d2/fragment/form", methods=("GET",))
async def cmd_d2_form():
    # Форма живёт в воркспейсе: нет валидной сессии — на выбор воркспейса.
    org = await _d2_session_org()
    if not org:
        return redirect("/d2")

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
        # Шаблон чужой орги (или без орги) — игнорируем: чистая форма.
        if template and (template.get("ORG") or DEFAULT_ORG_NAME) == org:
            template_title = template.get("TITLE") or ""
            inquiry = template.get("BODY") or ""

    user_weight = 1 if await _d2_edit_allowed(org) else 0
    statuses_list = [(status_, "") for status_ in statuses]

    from other.grist_tools import grist_manager, MTLGrist

    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    next_number = _org_next_number(questions, org)

    return await render_template(
        "d2_form.html",
        question_number=next_number,
        short_subject="",
        inquiry=inquiry,
        template_title=template_title,
        reading=1,
        readings_total=_org_readings(org),
        statuses=statuses_list,
        user_weight=user_weight,
        **await _d2_workspace_context(),
    )


@blueprint.route("/d2/number", methods=("GET",))
async def cmd_d2_get_number():
    from other.grist_tools import grist_manager, MTLGrist

    org = await _d2_session_org()
    if not org:
        return jsonify({"number": "1"})
    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    return jsonify({"number": str(_org_next_number(questions, org))})


@blueprint.route("/d2/add", methods=("POST",))
async def cmd_d2_add():
    session["return_to"] = request.url

    # Орга вопроса — воркспейс из сессии, org из формы не читается.
    org = await _d2_session_org()
    if not org:
        await flash("Сначала выберите организацию (воркспейс).")
        return redirect("/d2")

    form_data = await request.form
    question_number = form_data["question_number"]
    short_subject = form_data["short_subject"]
    inquiry = form_data["inquiry"]
    status = form_data["status"]
    reading = int(form_data["reading"])
    as_draft = form_data.get("as_draft") == "on"

    if not await _d2_edit_allowed(org):
        return redirect("/d2")

    from other.grist_tools import grist_manager, MTLGrist

    questions, question_data, _ = await _load_question_tables()
    # Номер уникален внутри орги (per-org нумерация); совпадение в чужой
    # орге не конфликт.
    if any(
        str(q.get("NUMBER")) == str(question_number)
        and (q.get("ORG") or DEFAULT_ORG_NAME) == org
        for q in questions
    ):
        same_org_ids = {
            q["id"]
            for q in questions
            if str(q.get("NUMBER")) == str(question_number)
            and (q.get("ORG") or DEFAULT_ORG_NAME) == org
        }
        existing = next(
            (r for r in question_data if r.get("QUESTION_ID") in same_org_ids),
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
                        "ORG": org,
                    }
                }
            ]
        },
    )
    _d2_invalidate_cache()
    questions, _, _ = await _load_question_tables()
    question_id = next(
        q["id"]
        for q in questions
        if str(q.get("NUMBER")) == str(question_number)
        and (q.get("ORG") or DEFAULT_ORG_NAME) == org
    )
    logger.info(
        f"D2 add: вопрос №{question_number} [{org}] создан, "
        f"QUESTION_ID={question_id}, draft={bool(as_draft)}"
    )

    # 2. Сообщение в Telegram (кроме черновика): sendRichMessage, фолбэк —
    # sendMessage+SULGUK.
    message_id = None
    channel = None
    if not as_draft:
        channel = await resolve_channel(org, reading)
        if channel is not None:
            message_id = await _d2_send_rich(
                channel, status, inquiry, org=org, reading=reading,
                question_number=question_number, title=short_subject,
                uuid_url=d_uuid, username=username,
            )
            if message_id is None:
                text = get_full_text(status, inquiry, [[], [], []], d_uuid, username)
                message_id = await _d2_send_legacy(channel, text)

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
    if message_id is not None and channel is not None:
        fields["TELEGRAM_LINK"] = f"https://t.me/c/{channel}/{message_id}"
    # 3. Строка в QUESTION_DATA.
    await grist_manager.post_data(
        MTLGrist.QUESTION_DATA, {"records": [{"fields": fields}]}
    )
    _d2_invalidate_cache()
    logger.info(
        f"D2 add: чтение reading={reading} uuid={d_uuid} "
        f"QUESTION_ID={question_id} [{org}], telegram_link={fields.get('TELEGRAM_LINK')!r}"
    )

    if as_draft:
        await flash("Черновик сохранён без публикации в Telegram.", "good")
    elif message_id is None:
        await flash("Error with telegram publishing")
    else:
        await flash("Вопрос успешно добавлен.", "good")
    return redirect(f"/d2/{d_uuid}")


D2_IMAGE_MAX_SIZE = 5 * 1024 * 1024  # 5 МБ
D2_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
# Магические байты: content-type клиенту не доверяем, но расширение/тип
# определяем по заголовку файла (sniffing).
D2_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _d2_sniff_image_type(data: bytes) -> str | None:
    """MIME по магическим байтам; webp определяется по RIFF-контейнеру."""
    for magic, mime in D2_IMAGE_MAGIC:
        if data.startswith(magic):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@blueprint.route("/d2/upload_image", methods=("POST",))
async def cmd_d2_upload_image():
    org = await _d2_session_org()
    if not org or not await _d2_edit_allowed(org):
        return jsonify({"error": "forbidden"}), 403

    files = await request.files
    upload = files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "no file"}), 400

    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in D2_IMAGE_TYPES:
        return jsonify({"error": "unsupported type"}), 400

    data = upload.read()
    if len(data) > D2_IMAGE_MAX_SIZE:
        return jsonify({"error": "too large"}), 413
    if _d2_sniff_image_type(data) is None:
        return jsonify({"error": "not an image"}), 400

    from other.grist_tools import grist_manager, MTLGrist

    try:
        row_id = await grist_manager.post_attachment(
            MTLGrist.D2_IMAGES,
            data,
            upload.filename,
            {
                "ORG": org,
                "UPLOADED_BY": "@" + session["userdata"]["username"],
                "CREATED_AT": datetime.now().isoformat(),
            },
        )
    except Exception as e:
        logger.info(f"D2 image upload error: {e}")
        return jsonify({"error": "upload failed"}), 502
    return jsonify({"url": f"/d2/img/{row_id}"})


@blueprint.route("/d2/img/<int:row_id>", methods=("GET",))
async def cmd_d2_img(row_id: int):
    """Публичная отдача картинки (анонимы из TG-поста); прокси к Grist."""
    from other.grist_tools import grist_manager, MTLGrist

    try:
        records = await grist_manager.load_table_data(MTLGrist.D2_IMAGES) or []
    except Exception as e:
        logger.info(f"D2 image lookup error: {e}")
        return abort(404)
    record = next((r for r in records if r.get("id") == row_id), None)
    # Attachment-поле Grist приходит в разных формах: 4, [4], {"id": 4} или
    # ['L', 4] (внутренний формат CelldRef: 'L' — тип, далее число).
    file_ref = (record or {}).get("FILE")

    def _extract_int(ref):
        if isinstance(ref, int):
            return ref
        if isinstance(ref, dict):
            return ref.get("id")
        if isinstance(ref, (list, tuple)):
            ints = [x for x in ref if isinstance(x, int)]
            return ints[0] if ints else None
        return None

    file_ref = _extract_int(file_ref)
    if not isinstance(file_ref, int):
        return abort(404)

    try:
        data = await grist_manager.get_attachment(MTLGrist.D2_IMAGES, file_ref)
    except Exception as e:
        logger.info(f"D2 image fetch error: {e}")
        return abort(404)

    media_type = _d2_sniff_image_type(data) or "application/octet-stream"
    return Response(
        data,
        mimetype=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@blueprint.route("/d2/copy", methods=("GET",))
async def cmd_d2_copy():
    data_row, question = await _find_question_row(request.args.get("uuid", ""))
    if data_row is None or question is None:
        return "Decision not exist =(", 404
    org = question.get("ORG") or DEFAULT_ORG_NAME
    if not await _org_visible(org):
        return "Decision not exist =(", 404

    user_weight = 1 if await _d2_edit_allowed(org) else 0
    statuses_list = [(status_, "") for status_ in statuses]

    from other.grist_tools import grist_manager, MTLGrist

    questions = await grist_manager.load_table_data(MTLGrist.QUESTIONS) or []
    # Копия живёт в орге исходного вопроса — номер следующий в этой орге.
    next_number = _org_next_number(questions, org)

    return await render_template(
        "d2_form.html",
        question_number=next_number,
        short_subject=(question.get("TITLE") or "") + " (копия)",
        inquiry=data_row.get("BODY") or "",
        template_title=f"Копия вопроса №{question.get('NUMBER')}",
        reading=1,
        statuses=statuses_list,
        user_weight=user_weight,
        org=org,
    )


@blueprint.route("/d2/template/from", methods=("POST",))
async def cmd_d2_template_from():
    form_data = await request.form
    template_uuid = form_data.get("uuid", "")
    title = (form_data.get("title") or "").strip()

    data_row, question = await _find_question_row(template_uuid)
    if data_row is None or question is None:
        return "Decision not exist =(", 404
    org = question.get("ORG") or DEFAULT_ORG_NAME
    if not await _org_visible(org):
        return "Decision not exist =(", 404

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
    _d2_invalidate_cache()
    await flash("Шаблон сохранён.", "good")
    return redirect(f"/d2/{template_uuid}")


@blueprint.route("/d2/fragment/edit", methods=("GET",))
async def cmd_d2_edit():
    # Список живёт в воркспейсе: нет валидной сессии — на выбор воркспейса.
    session_org = await _d2_session_org()
    if not session_org:
        return redirect("/d2")

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
                "telegram_link": row.get("TELEGRAM_LINK") or "",
            }
        )

    items = []
    for question in questions:
        number = question.get("NUMBER")
        title = question.get("TITLE") or ""
        question_id = question.get("id")
        org = question.get("ORG") or DEFAULT_ORG_NAME
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
                "org": org,
                "readings_count": len(readings),
                "uuids": [r["uuid"] for r in data_by_question.get(question_id, [])],
                # Клик по теме — на последнее чтение (текущая работа).
                "first_uuid": (
                    sorted(readings, key=lambda r: r["reading"])[-1]["uuid"]
                    if readings
                    else ""
                ),
                "is_draft": bool(readings)
                and all(not r["telegram_link"] for r in readings),
            }
        )

    items.sort(key=lambda row: (row["number"] is None, row["number"]), reverse=True)

    # Воркспейс-модель: только вопросы текущей организации.
    items = [row for row in items if row["org"] == session_org]

    status_param = request.args.get("status")
    query = (request.args.get("q") or "").strip().lower()
    explicit_status = bool(status_param)  # владелец сам выбрал статус
    # Статус применяется только если юзер ВЫБРАЛ его в комбобоксе
    # (onchange ставит status_changed=1). Enter в поле поиска сабмитит
    # форму без флага — тогда q ищет по всем, что бы ни было отрисовано
    # в селекте (иначе дефолтный «Требует внимания» тащился бы в каждый
    # поиск; решение владельца 2026-10-11).
    status_selected = request.args.get("status_changed") == "1"
    if not status_selected:
        status_param = None
        explicit_status = False
    # Поиск (решение владельца 2026-10-11): ищем по всем вопросам всех
    # статусов. Явный статус ПОВЕРХ поиска сужает найденное (выбрал
    # «Требует внимания» после поиска → из найденных только active/control).
    # Поиск без явного статуса — просто по всем.
    if query:
        filtered = items
        if explicit_status:
            if status_param == "active":
                filtered = [
                    row for row in items
                    if row["status"] in ("❗️ #active", "‼️ #control")
                ]
            elif status_param == "drafts":
                filtered = [row for row in items if row["is_draft"]]
            elif status_param == "all":
                pass
            elif status_param in statuses:
                filtered = [
                    row for row in items if row["status"] == status_param
                ]
    else:
        # Явный выбор статуса — уважается всегда. Без параметров — дефолт
        # вида «Требует внимания» с ПРИМЕНЁННЫМ фильтром (active+control),
        # иначе вид показывает один статус, а данные — все.
        if status_param == "active" or not status_param:
            # «Требует внимания»: активные + контроль (решение владельца
            # 2026-10-10; ☑️ #next — конечный статус, в агрегат не входит).
            filtered = [
                row for row in items
                if row["status"] in ("❗️ #active", "‼️ #control")
            ]
        elif status_param == "drafts":
            # Черновики: все чтения без TELEGRAM_LINK.
            filtered = [row for row in items if row["is_draft"]]
        elif status_param == "all":
            filtered = items
        elif status_param in statuses:
            filtered = [row for row in items if row["status"] == status_param]
        else:
            filtered = items

    if query:
        filtered = [
            row
            for row in filtered
            if query in str(row["title"]).lower() or query in str(row["number"]).lower()
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

    if query and not explicit_status:
        # Поиск без явного статуса: комбобокс на «Все» (фильтр не применён).
        status_filter = "all"
    elif status_param == "drafts":
        status_filter = "drafts"
    elif not explicit_status:
        # Нет явного выбора: дефолт вида «Активные», но фильтр статуса не применён
        # (поиск без статуса ищет по всем).
        status_filter = "active"
    else:
        status_filter = status_param

    return await render_template(
        "d2_frag_edit.html",
        items=page_items,
        current_uuid=request.args.get("uuid"),
        page=page,
        total_pages=total_pages,
        total_items=len(filtered),
        status_filter=status_filter,
        query=query,
        statuses=statuses,
        d2_hide_list_link=True,
        **await _d2_workspace_context(),
    )


@blueprint.route("/d2/fragment/new", methods=("GET",))
async def cmd_d2_new():
    # Пикер живёт в воркспейсе: нет валидной сессии — на выбор воркспейса.
    session_org = await _d2_session_org()
    if not session_org:
        return redirect("/d2")

    from other.grist_tools import grist_manager, MTLGrist

    templates = await grist_manager.load_table_data(MTLGrist.QUESTION_TEMPLATES) or []
    items = []
    for template in templates:
        # Чужие шаблоны прячутся целиком (решение владельца, раунд 1 Q4).
        if (template.get("ORG") or DEFAULT_ORG_NAME) != session_org:
            continue
        items.append(
            {
                "id": template.get("id"),
                "title": template.get("TITLE") or "",
                "body": template.get("BODY") or "",
            }
        )

    items.sort(key=lambda row: row["title"].lower())
    # Ни одного шаблона у орги — показываем простой дефолт (решение
    # владельца 2026-10-09); есть хоть один — дефолт не показываем.
    show_default = not items
    return await render_template(
        "d2_frag_new.html",
        templates=items,
        show_default=show_default,
        **await _d2_workspace_context(),
    )


@blueprint.route("/d/<decision_id>", methods=("GET", "POST"))
async def cmd_show_decision(decision_id):
    """Cutover-алиас (решение владельца 2026-10-11): /d/<uuid> отдаёт d2.
    Старые ссылки из постов (в т.ч. будущие rich-подвалы /d/<uuid>) ведут
    в d2-механизм; после вырезания d1 роут остаётся каноничным."""
    if len(decision_id) != 32:
        abort(404)
    return redirect(f"/d2/{decision_id}")
