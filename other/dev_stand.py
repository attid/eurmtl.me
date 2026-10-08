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
    doc_tables = _TABLES.setdefault(doc_id, {})
    rows = doc_tables.setdefault(table_name, [])
    next_id = max((r["id"] for r in rows), default=0) + 1
    for record in payload.get("records", []):
        rows.append({"id": next_id, "fields": dict(record.get("fields", {}))})
        next_id += 1
    return jsonify({}), 200


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


@blueprint.route("/dev/tg-log", methods=("GET",))
async def tg_log_page():
    rows = "".join(
        f"<tr><td>{entry['ts']}</td><td>{entry['method']}</td>"
        f"<td><code>{entry['payload']}</code></td></tr>"
        for entry in reversed(TG_CALL_LOG)
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>TG log</title><style>
body{{font-family:monospace;margin:1rem}}table{{border-collapse:collapse}}
td,th{{border:1px solid #999;padding:4px 8px;vertical-align:top}}
</style></head><body>
<h2>TG-мок: что улетело бы в Telegram</h2>
<table><tr><th>Время</th><th>Метод</th><th>Payload</th></tr>{rows}</table>
</body></html>"""


def tg_mock_record(method: str, payload: dict) -> dict:
    """Фиксирует вызов TG API в журнале. Возвращает фиктивный ответ Telegram."""
    entry = {
        "ts": time.strftime("%H:%M:%S"),
        "method": method,
        "payload": json.dumps(payload, ensure_ascii=False),
    }
    TG_CALL_LOG.append(entry)
    # aiogram шлёт camelCase-имена методов API: sendMessage, editMessageText.
    if method in ("sendMessage", "editMessageText"):
        # Поля ровно те, что требует pydantic-схема aiogram Message.
        return {
            "ok": True,
            "result": {
                "message_id": payload.get("message_id", 1000 + len(TG_CALL_LOG)),
                "date": int(time.time()),
                "chat": {"id": payload.get("chat_id", 0), "type": "private"},
                "text": payload.get("text", ""),
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
