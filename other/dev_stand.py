"""Тестовый Grist-двойник: in-memory таблицы + TG-мок для локального стенда.

Только ENVIRONMENT=test. Публикуется blueprint'ом в основном приложении:

- GET/POST/PATCH/PUT /docs/<doc_id>/tables/<table>/records — формат Grist API,
  совместим с other.grist_tools.GristAPI (fetch_data/post_data/patch_data).
- /dev/tg-log — страница с журналом «телеграмных» вызовов (send_message,
  edit_message_text), куда aiogram-боты ходят через TELEGRAM_API_URL.

Данные не персистятся: перезапуск стенда = чистый сид.
"""

import json
import time

from quart import Blueprint, jsonify, request

blueprint = Blueprint("dev_stand", __name__)

# Журнал вызовов Telegram API (send_message, edit_message_text, ...).
TG_CALL_LOG: list[dict] = []

# in-memory данные: {doc_id: {table_name: [{"id": int, "fields": {...}}]}}
_TABLES: dict[str, dict[str, list[dict]]] = {}
# URL, который пропишем таблицам MTLGrist в тест-режиме.
LOCAL_BASE_URL = "http://localhost:8000/api/docs"

# Схема колонок продового Grist-дока 3Fk4hjCv847GBx8ZTCPN2Y: дабл отвергает
# неизвестные поля, как реальный Grist (400), чтобы расхождение код↔схема
# ловилось тестами, а не продой. Д2-таблицы поддерживать при изменении схемы.
_D2_SCHEMAS: dict[str, set[str]] = {
    "D2_QUESTIONS": {"NUMBER", "TITLE", "READING", "ORG"},
    "D2_QUESTION_DATA": {
        "QUESTION_ID",
        "READING",
        "UUID",
        "TELEGRAM_LINK",
        "BODY",
        "STATUS",
        "EXTRA",
        "CREATED_BY",
        "CREATED_AT",
    },
    "D2_QUESTION_TEMPLATES": {"TITLE", "BODY", "ORG"},
    "D2_IMAGES": {"FILE", "ORG", "UPLOADED_BY", "CREATED_AT"},
}


def _unknown_columns(table_name: str, payload: dict) -> list[str]:
    """Поля POST-записей, которых нет в продовой схеме таблицы."""
    known = _D2_SCHEMAS.get(table_name)
    if known is None:
        return []
    unknown = set()
    for record in payload.get("records", []):
        unknown |= set(record.get("fields", {})) - known
    return sorted(unknown)


def load_seed(path: str) -> None:
    """Загружает сид-данные из JSON: {doc_id: {table: [ {field: value} ]}}."""
    with open(path, encoding="utf-8") as fh:
        seed = json.load(fh)
    for doc_id, tables in seed.items():
        doc_tables = _TABLES.setdefault(doc_id, {})
        for table_name, rows in tables.items():
            doc_tables[table_name] = [
                {"id": idx + 1, "fields": dict(row)} for idx, row in enumerate(rows)
            ]


def _records_response(rows: list[dict]) -> dict:
    return {"records": [{"id": r["id"], "fields": r["fields"]} for r in rows]}


@blueprint.route("/api/docs/<doc_id>/tables/<table_name>/records", methods=("GET",))
async def grist_fetch(doc_id: str, table_name: str):
    rows = _TABLES.get(doc_id, {}).get(table_name, [])
    # filter={"QUESTION_ID": [12]} — фильтр по точному совпадению поля.
    raw_filter = request.args.get("filter")
    if raw_filter:
        try:
            filter_dict = json.loads(raw_filter)
        except ValueError:
            filter_dict = {}
        for column, values in filter_dict.items():
            wanted = set(values)
            rows = [r for r in rows if r["fields"].get(column) in wanted]
    return jsonify(_records_response(rows))


@blueprint.route("/api/docs/<doc_id>/tables/<table_name>/records", methods=("POST",))
async def grist_post(doc_id: str, table_name: str):
    payload = await request.get_json()
    unknown = _unknown_columns(table_name, payload)
    if unknown:
        # Реальный Grist тоже отвечает 400 на несуществующие колонки.
        return jsonify({"error": f"Invalid fields: {', '.join(unknown)}"}), 400
    doc_tables = _TABLES.setdefault(doc_id, {})
    rows = doc_tables.setdefault(table_name, [])
    next_id = max((r["id"] for r in rows), default=0) + 1
    created = []
    for record in payload.get("records", []):
        rows.append({"id": next_id, "fields": dict(record.get("fields", {}))})
        created.append({"id": next_id})
        next_id += 1
    # Grist отвечает {"records": [{"id": N}, ...]} — этим пользуются клиенты.
    return jsonify({"records": created}), 200


def _apply_updates(rows: list[dict], payload: dict, with_fields: bool) -> None:
    for record in payload.get("records", []):
        record_id = record.get("id")
        if with_fields and record_id is not None:
            # PATCH {"records": [{"id": N, "fields": {...}}]}
            for row in rows:
                if row["id"] == record_id:
                    row["fields"].update(record.get("fields", {}))
                    break
        elif not with_fields:
            # PUT {"records": [{"id": N, "fields": {...}}]} или {"fields": ...}
            for row in rows:
                if row["id"] == record_id:
                    row["fields"] = dict(record.get("fields", {}))
                    break


@blueprint.route("/api/docs/<doc_id>/tables/<table_name>/records", methods=("PATCH",))
async def grist_patch(doc_id: str, table_name: str):
    payload = await request.get_json()
    rows = _TABLES.get(doc_id, {}).get(table_name, [])
    _apply_updates(rows, payload, with_fields=True)
    return jsonify({}), 200


@blueprint.route("/api/docs/<doc_id>/tables/<table_name>/records", methods=("PUT",))
async def grist_put(doc_id: str, table_name: str):
    payload = await request.get_json()
    rows = _TABLES.get(doc_id, {}).get(table_name, [])
    _apply_updates(rows, payload, with_fields=False)
    return jsonify({}), 200


# in-memory аттачменты двойника: {doc_id: {attachment_id: (bytes, filename)}}
_ATTACHMENTS: dict[str, dict[int, tuple[bytes, str]]] = {}
_ATTACHMENTS_NEXT_ID = {"n": 1}


@blueprint.route("/api/docs/<doc_id>/attachments", methods=("POST",))
async def grist_attachments_post(doc_id: str):
    """Grist-совместимая загрузка вложений: multipart "upload" -> [{"id": N}]."""
    files = await request.files
    uploads = files.getlist("upload")
    if not uploads:
        return jsonify({"error": "no file"}), 400
    doc = _ATTACHMENTS.setdefault(doc_id, {})
    ids = []
    for f in uploads:
        att_id = _ATTACHMENTS_NEXT_ID["n"]
        _ATTACHMENTS_NEXT_ID["n"] += 1
        doc[att_id] = (f.read(), f.filename or "upload.bin")
        ids.append({"id": att_id})
    return jsonify(ids)


@blueprint.route(
    "/api/docs/<doc_id>/attachments/<int:attachment_id>/download", methods=("GET",)
)
async def grist_attachment_download(doc_id: str, attachment_id: int):
    entry = _ATTACHMENTS.get(doc_id, {}).get(attachment_id)
    if entry is None:
        return jsonify({"error": "not found"}), 404
    data, filename = entry
    from quart import Response

    return Response(
        data,
        mimetype="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@blueprint.route("/dev/tg-log", methods=("GET",))
async def tg_log_page():
    """Читаемый журнал: UTF-8 без эскейпов, rich_message раскрыт в
    структурированный вид (блоки построчно), JSON — с отступами."""
    rows = []
    for entry in reversed(TG_CALL_LOG):
        payload_raw = entry["payload"]
        try:
            payload = json.loads(payload_raw)
        except (ValueError, TypeError):
            payload = payload_raw

        rich_html = ""
        if isinstance(payload, dict) and "rich_message" in payload:
            try:
                rich = json.loads(payload["rich_message"])
                blocks = rich.get("blocks", [])
                parts = [
                    f'<div class="rich-head">rich_message: {len(blocks)} блоков</div>'
                ]
                for i, block in enumerate(blocks):
                    text = _block_rich_html(block)
                    btype = block.get("type", "?")
                    extra = ""
                    if btype == "photo":
                        extra = " 🖼"
                    if block.get("spoiler"):
                        extra += " (spoiler)"
                    btype_label = {
                        "blockquote": "цитата",
                        "expandable_blockquote": "сворачиваемая цитата",
                        "pre": "блок кода",
                        "heading": f"заголовок (size={block.get('size', '?')})",
                    }.get(btype, btype)
                    parts.append(
                        f'<div class="rich-block"><span class="btype">{i + 1}. '
                        f"{btype_label}{extra}</span>{text}</div>"
                    )
                rich_html = "".join(parts)
            except (ValueError, TypeError):
                rich_html = '<div class="rich-head">rich_message (не JSON)</div>'
            payload_view = _html_escape(
                json.dumps(
                    {k: v for k, v in payload.items() if k != "rich_message"},
                    ensure_ascii=False,
                )
            )
        else:
            payload_view = _html_escape(
                json.dumps(payload, ensure_ascii=False, indent=2)
                if isinstance(payload, dict)
                else str(payload)
            )

        rows.append(
            f'<details class="call"><summary>'
            f'<span class="ts">{entry["ts"]}</span> '
            f'<span class="method">{entry["method"]}</span>'
            f"</summary>"
            f"{rich_html}"
            f'<pre class="payload">{payload_view}</pre>'
            f"</details>"
        )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>TG log</title><style>
body{{font-family:system-ui,sans-serif;margin:1rem;background:#1a1e25;color:#e6e6e6}}
h2{{color:#fff}}
.call{{border:1px solid #3a4048;border-radius:6px;margin:8px 0;background:#232830}}
summary{{cursor:pointer;padding:8px 12px;font-family:monospace}}
summary:hover{{background:#2a3038}}
.ts{{color:#888;margin-right:12px}}
.method{{color:#4fc3f7;font-weight:bold}}
.rich-head{{color:#ffb74d;font-family:monospace;padding:4px 12px;font-size:0.9em}}
.rich-block{{padding:4px 12px;border-left:3px solid #4fc3f7;margin:6px 12px;white-space:pre-wrap}}
.btype{{display:inline-block;color:#888;font-family:monospace;font-size:0.85em;margin-right:8px}}
.mk-tag{{color:#ffb74d;font-family:monospace;font-size:0.8em}}
.mk-spoiler{{background:#666;color:transparent;border-radius:2px}}
.mk-spoiler:hover{{color:inherit}}
.payload{{padding:8px 12px;white-space:pre-wrap;word-break:break-word;font-size:0.85em;
color:#a5b2c0;margin:0;border-top:1px solid #3a4048}}
</style></head><body>
<h2>TG-мок: что улетело бы в Telegram</h2>
<p><em>Кликни по записи — раскроется содержимое. rich_message показан блоками.</em></p>
{"".join(rows)}
</body></html>"""


def _block_rich_html(block: dict) -> str:
    """Блок → HTML с видимыми признаками форматов: [жирный], [спойлер],
    [цитата], [код], [ссылка: url] и т.д. — чтобы в журнале было видно,
    какие теги реально дошли."""
    parts: list[str] = []

    def fmt(text: str, wrapper: str) -> str:
        label = {
            "bold": "жирный",
            "italic": "курсив",
            "underline": "подчёркнутый",
            "strikethrough": "зачёркнутый",
            "spoiler": "СПОЙЛЕР",
            "code": "код",
            "url": "ссылка",
        }.get(wrapper, wrapper)
        if wrapper == "spoiler":
            return f'<span class="mk-spoiler">{text}</span>'
        if wrapper == "url":
            return f'<span class="mk-tag">[ссылка]</span>{text}'
        return f'<span class="mk-tag">[{label}]</span>{text}'

    def walk(node):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            t = node.get("type")
            if "text" in node:
                inner = node["text"]
                # внутренности тоже могут быть узлами (concat)
                before = len(parts)
                walk(inner)
                if t and len(parts) > before:
                    parts[before] = (
                        fmt(parts[before], t)
                        if isinstance(parts[before], str)
                        else parts[before]
                    )
            elif "source" in node:  # math
                parts.append(f'<span class="mk-tag">[math]</span>{node["source"]}')
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(block.get("text"))
    if not parts and "blocks" in block:
        for inner in block.get("blocks", []):
            parts.append(_block_rich_html(inner))
    return "".join(parts)


def _block_plain_text(block: dict) -> str:
    """Читаемый текст rich-блока: обходит дерево узлов, склеивает text/plain."""
    parts: list[str] = []

    def walk(node):
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, dict):
            if "text" in node:
                walk(node["text"])
            if "source" in node:  # math
                parts.append(str(node["source"]))
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(block.get("text"))
    if not parts and "blocks" in block:
        for inner in block["blocks"]:
            walk(inner.get("text") if isinstance(inner, dict) else inner)
    return "".join(parts)


def _html_escape(value: str) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@blueprint.route("/dev/tg-log/json", methods=("GET",))
async def tg_log_json():
    """Журнал вызовов в машинном виде (для скриптов: ресенд, диффы)."""
    return jsonify({"calls": TG_CALL_LOG})


def tg_mock_record(method: str, payload: dict) -> dict:
    """Фиксирует вызов TG API в журнале. Возвращает фиктивный ответ Telegram."""
    entry = {
        "ts": time.strftime("%H:%M:%S"),
        "method": method,
        "payload": json.dumps(payload, ensure_ascii=False),
    }
    TG_CALL_LOG.append(entry)
    # aiogram шлёт camelCase-имена методов API: sendMessage, editMessageText,
    # sendRichMessage.
    if method in ("sendMessage", "editMessageText"):
        # Поля ровно те, что требует pydantic-схема aiogram Message.
        return {
            "ok": True,
            "result": {
                "message_id": payload.get("message_id", 1000 + len(TG_CALL_LOG)),
                "date": int(time.time()),
                "chat": {"id": payload.get("chat_id", 0), "type": "private"},
                "text": payload.get(
                    "text", "rich" if payload.get("rich_message") else ""
                ),
            },
        }
    if method == "sendRichMessage":
        # rich_message приходит строкой (JSON) в multipart-форме; Message
        # требует message_id/date/chat — text фиктивный.
        rich = payload.get("rich_message", "")
        try:
            blocks = len(json.loads(rich).get("blocks", [])) if rich else 0
        except ValueError:
            blocks = 0
        return {
            "ok": True,
            "result": {
                "message_id": 1000 + len(TG_CALL_LOG),
                "date": int(time.time()),
                "chat": {"id": payload.get("chat_id", 0), "type": "private"},
                "text": f"rich ({blocks} blocks)",
            },
        }
    return {"ok": True, "result": True}


def activate_stand() -> None:
    """Переключает Grist-таблицы и TG-ботов на локальный стенд.

    Вызывается один раз при старте приложения в test-режиме, до первого запроса.
    """
    from other.grist_tools import MTLGrist

    # Grist: все таблицы MTLGrist начинают указывать на локальный двойник.
    for attr in vars(MTLGrist):
        if attr.startswith("_"):
            continue
        table = getattr(MTLGrist, attr)
        if hasattr(table, "base_url"):
            table.base_url = LOCAL_BASE_URL

    # Telegram: боты ходят в локальный мок-роут основного приложения.
    from other import telegram_tools

    local_tg = "http://localhost:8000/bot-api"
    telegram_tools._TELEGRAM_API_URL = local_tg
    from aiogram.client.session.aiohttp import AiohttpSession
    from aiogram.client.telegram import TelegramAPIServer

    for bot in (telegram_tools.skynet_bot, telegram_tools.mmwb_bot):
        bot.session = AiohttpSession(api=TelegramAPIServer.from_base(local_tg))

    # Тест-юзер = itolstov (сид: Users[0].telegram_id) — чтобы гейты
    # подписантов/секретарей проходили без реального Telegram-логина.
    from other.config_reader import config

    config.test_user_id = 1837984392

    # Stellar: вес подписчика не должен зависеть от реального хорайзона.
    import services.stellar_client as stellar_client

    async def _stand_fund_signers():
        return {
            "signers": [
                {
                    "key": "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V",
                    "weight": 1,
                    "telegram_id": 1837984392,
                }
            ]
        }

    stellar_client.get_fund_signers = _stand_fund_signers


def register_tg_mock(app) -> None:
    """Ловит вызовы aiogram-ботов и отвечает фиктивным Telegram-ответом."""

    @app.route("/bot-api/bot<token>/<method>", methods=("POST",))
    async def bot_api_mock(token: str, method: str):
        # aiogram шлёт multipart-form, не JSON.
        form = await request.form
        payload = {k: v for k, v in form.items()}
        return jsonify(tg_mock_record(method, payload))
