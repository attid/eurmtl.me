"""D2: публичный embed-список вопросов орги по секретному токену.

Замена гугло-дока MTLFUND, который встраивали фреймом на сторонний сайт.
Анонимный read-only: токен орги (32 hex) хранится в Grist-таблице D2_PUBLIC,
владелец генерит и ротирует руками в UI. Публично только чтение: № / тема /
статус / ссылки на TG-посты чтений. Тексты вопросов (BODY) и прочие
служебные поля (CREATED_BY, UUID, EXTRA) не рендерятся нигде. Вопрос без
ни одного опубликованного чтения (все TELEGRAM_LINK пусты) не показывается.
"""

import hmac

from quart import Blueprint, abort, render_template, Response

from other.cache_tools import AsyncTTLCache

blueprint = Blueprint("d2_public", __name__)

# 5 секунд, как question_tables_cache у воркспейса: обновление токена/данных
# в Grist подхватывается без деплоя, embed-страницы не дёргают Grit на каждый
# показ.
public_tables_cache = AsyncTTLCache(ttl_seconds=5)


async def _load_public_tables():
    """(public_rows, questions, question_data) из Grist с кешем 5с."""
    cached = await public_tables_cache.get("tables")
    if cached is not None:
        return cached
    from other.grist_tools import grist_manager, MTLGrist

    tables = (
        await grist_manager.load_table_data(MTLGrist.D2_PUBLIC) or [],
        await grist_manager.load_table_data(MTLGrist.QUESTIONS) or [],
        await grist_manager.load_table_data(MTLGrist.QUESTION_DATA) or [],
    )
    await public_tables_cache.set("tables", tables)
    return tables


@blueprint.route("/d2/pub/<token>", methods=("GET",))
async def d2_public_embed(token: str):
    rows, questions, question_data = await _load_public_tables()

    # Одинаковый ответ на любой неверный токен — без перечисления орг.
    # strip: токен в Grist вписывается руками, хвостовой пробел не должен
    # убивать ссылку; compare_digest: const-time сравнение секрета.
    org = next(
        (
            r.get("ORG")
            for r in rows
            if r.get("ORG")
            and hmac.compare_digest(str(r.get("TOKEN") or "").strip(), token)
        ),
        None,
    )
    if org is None:
        abort(404)

    org_questions = {q.get("id"): q for q in questions if q.get("ORG") == org}
    data_by_question: dict[int, list[dict]] = {}
    for row in question_data:
        question_id = row.get("QUESTION_ID")
        if question_id not in org_questions:
            continue
        try:
            reading = int(row.get("READING"))
        except (TypeError, ValueError):
            continue
        link = (row.get("TELEGRAM_LINK") or "").strip()
        # Grist-строки редактируются людьми: пропускаем только настоящие
        # tg-ссылки — отсекает javascript:/data: из битой ячейки.
        if not link.startswith(("https://t.me/", "https://telegram.me/")):
            continue
        data_by_question.setdefault(question_id, []).append(
            {"reading": reading, "status": row.get("STATUS") or "", "link": link}
        )

    items = []
    for question_id, question in org_questions.items():
        readings = data_by_question.get(question_id, [])
        if not readings:
            continue  # ни одного опубликованного чтения — не показываем
        readings.sort(key=lambda r: r["reading"])
        last = readings[-1]
        raw_num = question.get("NUMBER")
        try:
            num = int(raw_num) if str(raw_num or "").strip() else None
        except (TypeError, ValueError):
            num = None
        items.append(
            {
                "number": num,
                "title": question.get("TITLE") or "",
                "status": last["status"],
                "readings": readings,
            }
        )
    items.sort(
        key=lambda row: (row["number"] is None, row["number"] or 0), reverse=True
    )

    html = await render_template("d2_public.html", org=org, items=items)
    return Response(
        html,
        200,
        headers={
            # Токен и есть граница приватности: разрешаем встраивание
            # откуда угодно, от поисковиков закрываемся.
            "X-Robots-Tag": "noindex, nofollow",
            "Content-Security-Policy": "frame-ancestors *",
        },
    )
