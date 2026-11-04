"""MCP-совместимый JSON-RPC эндпоинт для AI-агентов.

Stateless: один POST = один вызов (initialize / tools/list / tools/call),
ответ — обычный JSON. Auth — Bearer-токен из t_api_tokens (см. routers/token.py).
Идентичность берётся из токена, права — те же функции, что у веба d2.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Callable

from loguru import logger
from quart import Blueprint, Response, jsonify, request

from other.grist_tools import DEFAULT_ORG_NAME
from routers.token import authenticate_bearer, scope_allows

blueprint = Blueprint("mcp", __name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_INFO = {"name": "eurmtl-me", "version": "1.0.0"}

# Заполнен внизу файла: {имя: (описание, json_schema, handler)}
TOOLS: dict[str, tuple[str, dict, Callable]] = {}


def _rpc_result(req_id, result: dict) -> Response:
    return jsonify({"jsonrpc": "2.0", "id": req_id, "result": result})


def _rpc_error(req_id, code: int, message: str) -> Response:
    return jsonify(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    )


class ToolError(Exception):
    """Ошибка вызова tool — уходит как JSON-RPC error, не как 500."""


# ---------------------------------------------------------------- Grist


async def _load_question_tables():
    """(questions, question_data) — единый loader веба (decision.py:489):
    один кеш, мутации MCP видны вебу сразу и наоборот."""
    from routers.decision import _load_question_tables as web_loader

    questions, question_data, _ = await web_loader()
    return questions, question_data


def _invalidate_cache() -> None:
    from routers.decision import _d2_invalidate_cache

    _d2_invalidate_cache()


def _readings_int(row) -> int | None:
    try:
        return int(row.get("READING"))
    except (TypeError, ValueError):
        return None


def _question_org(q: dict) -> str:
    return q.get("ORG") or DEFAULT_ORG_NAME


# ------------------------------------------------------- Права (как в вебе)


async def _identity_orgs(tg_id: int) -> set:
    """Орги, видимые носителю токена: подписант MAIN_ADDRESS или секретарь."""
    from other import orgs_config
    from other.grist_tools import user_org_names
    from routers.decision import _org_secretary_addresses

    visible = set(await user_org_names(tg_id))
    for org in orgs_config.ORGS:
        if org.name in visible or not org.main_address:
            continue
        if tg_id in await _org_secretary_addresses(org.name):
            visible.add(org.name)
    return visible


async def _d2_edit_allowed(tg_id: int, org: str) -> bool:
    """Точечная проверка (decision.py:134-146): секретарь орги или подписант."""
    if not org:
        return False
    from other.grist_tools import user_org_names
    from routers.decision import _org_secretary_addresses

    if tg_id in await _org_secretary_addresses(org):
        return True
    return org in set(await user_org_names(tg_id))


# ----------------------------------------------------------------- Tools


async def tool_d2_list_orgs(args: dict, tg_id: int, username: str) -> dict:
    from other import orgs_config

    visible = await _identity_orgs(tg_id)
    return {
        "orgs": [
            {"name": org.name, "can_edit": True}
            for org in orgs_config.ORGS
            if org.name in visible
        ]
    }


async def tool_d2_list_questions(args: dict, tg_id: int, username: str) -> dict:
    org = str(args.get("org") or "")
    if not await _d2_edit_allowed(tg_id, org):
        raise ToolError(f"org '{org}' недоступна")
    questions, question_data = await _load_question_tables()

    data_by_qid: dict[int, list] = {}
    for r in question_data:
        try:
            data_by_qid.setdefault(int(r["QUESTION_ID"]), []).append(r)
        except (TypeError, ValueError):
            continue  # пустая/битая ячейка QUESTION_ID в Grist

    result = []
    for q in questions:
        if _question_org(q) != org:
            continue
        readings = sorted(
            (r for r in data_by_qid.get(q["id"], []) if _readings_int(r) is not None),
            key=_readings_int,
        )
        last = readings[-1] if readings else {}
        result.append(
            {
                "number": q.get("NUMBER"),
                "title": q.get("TITLE") or "",
                "uuid": last.get("UUID") or "",
                "status": last.get("STATUS") or "",
                "is_draft": not (last.get("TELEGRAM_LINK") or ""),
                "readings": [(_readings_int(r) or 0) for r in readings],
            }
        )

    def _number_sort_key(val):
        if val is None:
            return (1, 0)
        try:
            return (0, int(val))
        except (TypeError, ValueError):
            return (0, 0)

    result.sort(key=lambda x: _number_sort_key(x["number"]))
    return {"org": org, "questions": result}


async def tool_d2_get_question(args: dict, tg_id: int, username: str) -> dict:
    uuid_ = str(args.get("uuid") or "").strip()
    if not uuid_:
        raise ToolError("поле 'uuid' обязательно")
    questions, question_data = await _load_question_tables()
    row = next((r for r in question_data if r.get("UUID") == uuid_), None)
    if row is None:
        raise ToolError(f"вопрос с uuid '{uuid_}' не найден")
    qid = row.get("QUESTION_ID")
    question = next(
        (q for q in questions if str(q.get("id")) == str(row.get("QUESTION_ID"))),
        None,
    )
    if question is None:
        raise ToolError(f"вопрос с uuid '{uuid_}' не найден")
    org = _question_org(question)
    if not await _d2_edit_allowed(tg_id, org):
        # Существование чужого вопроса не палим (как decision.py:565).
        raise ToolError(f"вопрос с uuid '{uuid_}' не найден")
    # Все чтения вопроса (как readings_nav в вебе, decision.py:573-580):
    # при смене reading веб создаёт новую строку с новым UUID, старая остаётся.
    rows = [r for r in question_data if str(r.get("QUESTION_ID")) == str(qid)]
    rows.sort(key=lambda r: _readings_int(r) or 0)
    return {
        "org": org,
        "number": question.get("NUMBER"),
        "title": question.get("TITLE") or "",
        "readings": [
            {
                "uuid": r.get("UUID"),
                "reading": _readings_int(r),
                "body": r.get("BODY") or "",
                "status": r.get("STATUS") or "",
                "created_by": r.get("CREATED_BY") or "",
                "created_at": r.get("CREATED_AT") or "",
                "telegram_link": r.get("TELEGRAM_LINK") or "",
                "is_draft": not (r.get("TELEGRAM_LINK") or ""),
            }
            for r in rows
        ],
    }


async def tool_d2_create_draft(args: dict, tg_id: int, username: str) -> dict:
    org = str(args.get("org") or "")
    title = str(args.get("title") or "").strip()
    body = str(args.get("body") or "")
    if not title:
        raise ToolError("поле 'title' обязательно")
    if not await _d2_edit_allowed(tg_id, org):
        raise ToolError(f"org '{org}' недоступна")

    from other.grist_tools import grist_manager, MTLGrist
    from routers.decision import _org_next_number, _org_readings

    questions, question_data = await _load_question_tables()

    number = args.get("number")
    if number is not None:
        try:
            number = int(number)
        except (TypeError, ValueError):
            raise ToolError(f"'number' должен быть целым числом, получено: {number!r}")
        if number < 1:
            raise ToolError(f"номер вопроса должен быть >= 1, получено: {number}")
        if any(
            str(q.get("NUMBER")) == str(number) and _question_org(q) == org
            for q in questions
        ):
            raise ToolError(f"номер {number} в org '{org}' уже занят")
    else:
        number = _org_next_number(questions, org)

    raw_reading = args.get("reading")
    try:
        reading = 1 if raw_reading is None else int(raw_reading)
    except (TypeError, ValueError):
        raise ToolError(
            f"'reading' должен быть целым числом, получено: {raw_reading!r}"
        )
    readings_total = _org_readings(org)
    max_reading = readings_total if readings_total > 0 else 1
    if reading < 1 or reading > max_reading:
        raise ToolError(
            f"reading {reading} вне диапазона org '{org}' (max={max_reading})"
        )

    created_by = "@" + username
    await grist_manager.post_data(
        MTLGrist.QUESTIONS,
        {
            "records": [
                {
                    "fields": {
                        "NUMBER": number,
                        "TITLE": title,
                        "READING": reading,
                        "ORG": org,
                    }
                }
            ]
        },
    )
    _invalidate_cache()
    questions, question_data = await _load_question_tables()
    question = next(
        (
            q
            for q in questions
            if str(q.get("NUMBER")) == str(number) and _question_org(q) == org
        ),
        None,
    )
    if question is None:
        raise ToolError(f"не удалось найти созданный вопрос №{number} в org '{org}'")
    question_id = question["id"]

    new_uuid = uuid.uuid4().hex
    await grist_manager.post_data(
        MTLGrist.QUESTION_DATA,
        {
            "records": [
                {
                    "fields": {
                        "QUESTION_ID": question_id,
                        "READING": reading,
                        "UUID": new_uuid,
                        "BODY": body,
                        "EXTRA": "",
                        "STATUS": "❗️ #active",
                        "CREATED_BY": created_by,
                        "CREATED_AT": datetime.now().isoformat(),
                    }
                }
            ]
        },
    )
    _invalidate_cache()
    logger.info(
        f"MCP d2_create_draft: №{number} [{org}] r={reading} uuid={new_uuid} "
        f"by @{username} (tg_id={tg_id})"
    )
    return {"uuid": new_uuid, "number": number, "org": org, "reading": reading}


async def tool_d2_update_draft(args: dict, tg_id: int, username: str) -> dict:
    uuid_ = str(args.get("uuid") or "").strip()
    if not uuid_:
        raise ToolError("поле 'uuid' обязательно")
    from other.grist_tools import grist_manager, MTLGrist

    questions, question_data = await _load_question_tables()
    row = next((r for r in question_data if r.get("UUID") == uuid_), None)
    if row is None:
        raise ToolError(f"чтение с uuid '{uuid_}' не найдено")
    if row.get("TELEGRAM_LINK"):
        raise ToolError(
            "это опубликованное чтение — правка только через веб (или owner)"
        )
    question = next(
        (q for q in questions if str(q.get("id")) == str(row.get("QUESTION_ID"))),
        None,
    )
    if question is None:
        raise ToolError(f"чтение с uuid '{uuid_}' не найдено")
    org = _question_org(question)
    if not await _d2_edit_allowed(tg_id, org):
        # Существование чужого вопроса не палим (как decision.py:565).
        raise ToolError(f"чтение с uuid '{uuid_}' не найдено")

    fields: dict[str, Any] = {}
    if "body" in args and args["body"] is not None:
        fields["BODY"] = str(args["body"])
    if "status" in args and args["status"] is not None:
        from routers.decision import statuses

        st = str(args["status"])
        if st not in statuses:
            raise ToolError(
                f"недопустимый статус '{st}', разрешены: {', '.join(statuses)}"
            )
        fields["STATUS"] = st
    clean_title = (
        str(args["title"]).strip()
        if ("title" in args and args["title"] is not None)
        else None
    )
    if clean_title is not None and not clean_title:
        raise ToolError("поле 'title' не может быть пустым")
    changed = False
    updated: list[str] = []
    if fields:
        await grist_manager.patch_data(
            MTLGrist.QUESTION_DATA, {"records": [{"id": row["id"], "fields": fields}]}
        )
        changed = True
        updated.extend(fields.keys())
    if clean_title is not None and question.get("TITLE") != clean_title:
        await grist_manager.patch_data(
            MTLGrist.QUESTIONS,
            {"records": [{"id": question["id"], "fields": {"TITLE": clean_title}}]},
        )
        changed = True
        updated.append("title")
    if changed:
        _invalidate_cache()
    logger.info(f"MCP d2_update_draft: uuid={uuid_} [{org}] by @{username}")
    return {"uuid": uuid_, "updated": updated}


# ------------------------------------------------------------- Реестр

TOOLS_LIST = [
    (
        "d2_list_orgs",
        "Организации (воркспейсы), доступные владельцу токена. Вызывай первым, "
        "чтобы узнать допустимые значения параметра org остальных tools.",
        {"type": "object", "properties": {}, "required": []},
        tool_d2_list_orgs,
    ),
    (
        "d2_list_questions",
        "Список вопросов организации: номер, тема, статус, черновик ли, "
        "чтения. Черновик — вопрос без публикации в Telegram.",
        {
            "type": "object",
            "properties": {
                "org": {
                    "type": "string",
                    "description": "имя организации из d2_list_orgs",
                }
            },
            "required": ["org"],
        },
        tool_d2_list_questions,
    ),
    (
        "d2_get_question",
        "Полные данные вопроса по uuid (uuid из d2_list_questions): все "
        "чтения с телом (HTML), статусами, автором. UUID последнего чтения "
        "нужен для d2_update_draft.",
        {
            "type": "object",
            "properties": {
                "uuid": {"type": "string", "description": "UUID чтения вопроса"}
            },
            "required": ["uuid"],
        },
        tool_d2_get_question,
    ),
    (
        "d2_create_draft",
        "Создать черновик вопроса (НЕ уходит в Telegram). title — короткая "
        "тема; body — HTML: каждый абзац обёрнут в свой <p>...</p>, "
        "plain-переносы \\n не визуализируются и текст без тегов склеится "
        "в один абзац. Разделы: <p><b>Предложение:</b> ...</p> и "
        "<p><b>Обоснование:</b> ...</p> (обязательны), при необходимости "
        "<p><b>Примечание:</b> ...</p> и <p><b>Имплементация:</b> ...</p>. "
        "number — необязательно (по умолчанию следующий "
        "свободный); reading — необязательно (по умолчанию 1). Возвращает uuid.",
        {
            "type": "object",
            "properties": {
                "org": {"type": "string"},
                "title": {"type": "string"},
                "body": {
                    "type": "string",
                    "description": "HTML; каждый абзац в своём <p>...</p> "
                    "(plain \\n не визуализируются). Разделы <p><b>Предложение:"
                    "</b> ...</p> и <p><b>Обоснование:</b> ...</p> обязательны.",
                },
                "number": {"type": "integer"},
                "reading": {"type": "integer"},
            },
            "required": ["org", "title", "body"],
        },
        tool_d2_create_draft,
    ),
    (
        "d2_update_draft",
        "Править черновик по uuid: title (тема), body (HTML, абзацы "
        "<p>...</p> — как в d2_create_draft), status. "
        "status — ровно одна из строк: '❗️ #active', '☑️ #next', '✅ #done', "
        "'🔂 #resign', '‼️ #control', '🔇 #canceled' (с эмодзи, как написано). "
        "Опубликованные чтения не правятся.",
        {
            "type": "object",
            "properties": {
                "uuid": {"type": "string"},
                "title": {"type": "string"},
                "body": {
                    "type": "string",
                    "description": "HTML; каждый абзац в своём <p>...</p> "
                    "(plain \\n не визуализируются). Разделы как в "
                    "d2_create_draft.",
                },
                "status": {
                    "type": "string",
                    "enum": [
                        "❗️ #active",
                        "☑️ #next",
                        "✅ #done",
                        "🔂 #resign",
                        "‼️ #control",
                        "🔇 #canceled",
                    ],
                },
            },
            "required": ["uuid"],
        },
        tool_d2_update_draft,
    ),
]

TOOLS = {name: (desc, schema, fn) for name, desc, schema, fn in TOOLS_LIST}

# ------------------------------------------------------------- JSON-RPC


async def _handle(req: dict, tg_id: int, username: str, scope: str):
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return _rpc_result(
            req_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": MCP_SERVER_INFO,
            },
        )

    if method == "tools/list":
        return _rpc_result(
            req_id,
            {
                "tools": [
                    {"name": n, "description": d, "inputSchema": s}
                    for n, (d, s, _fn) in TOOLS.items()
                ]
            },
        )

    if method == "tools/call":
        params = req.get("params")
        if not isinstance(params, dict):
            return _rpc_error(req_id, -32602, "params must be an object")
        name = params.get("name")
        tool = TOOLS.get(name)
        if tool is None:
            return _rpc_error(req_id, -32602, f"unknown tool: {name}")
        _desc, _schema, fn = tool
        if not scope_allows(scope, "d2"):
            return _rpc_error(req_id, -32602, f"token scope does not allow {name}")
        raw_args = params.get("arguments")
        if raw_args is None:
            args = {}
        elif not isinstance(raw_args, dict):
            return _rpc_error(req_id, -32602, "arguments must be an object")
        else:
            args = raw_args
        try:
            result = await fn(args, tg_id, username)
        except ToolError as e:
            return _rpc_result(
                req_id,
                {"content": [{"type": "text", "text": str(e)}], "isError": True},
            )
        except Exception as e:
            # Сбой Grist/сети/парсинга — ошибка tool, не 500.
            logger.exception(f"MCP tool {name} failed for @{username}")
            return _rpc_result(
                req_id,
                {
                    "content": [{"type": "text", "text": f"error: {e}"}],
                    "isError": True,
                },
            )
        return _rpc_result(
            req_id,
            {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                ],
            },
        )

    return _rpc_error(req_id, -32601, f"method not found: {method}")


@blueprint.route("/mcp", methods=("POST",))
async def mcp_endpoint():
    token = await authenticate_bearer(request.headers.get("Authorization"))
    if token is None:
        return jsonify({"error": "unauthorized"}), 401

    try:
        # force: клиенты агентов не всегда ставят Content-Type application/json.
        req = await request.get_json(force=True, silent=True)
    except Exception:
        req = None
    if req is None:
        return _rpc_error(None, -32700, "parse error")
    if (
        not isinstance(req, dict)
        or req.get("jsonrpc") != "2.0"
        or not req.get("method")
    ):
        return _rpc_error(
            req.get("id") if isinstance(req, dict) else None, -32600, "invalid request"
        )

    username = (token.username or "").lstrip("@")
    response = await _handle(req, int(token.tg_id), username, token.scope or "")
    params = req.get("params")
    tool_name = params.get("name", "-") if isinstance(params, dict) else "-"
    logger.info(
        f"MCP {req.get('method')}/{tool_name} by @{username} (tg_id={token.tg_id})"
    )
    return response
