"""D2: черновики и публикация/републикация вопросов."""

import pytest
from unittest.mock import AsyncMock, patch

DRAFT_UUID = "aaaabbbbccccddddeeeeffff00003333"  # вопрос №2, GORA, TELEGRAM_LINK=""
PUBLISHED_UUID = "aaaabbbbccccddddeeeeffff00001111"  # вопрос №1, PFM, чтение 1

# Реальные адреса организаций из orgs_config.
PFM_ADDRESS = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
GORA_ADDRESS = "GCVTXUMIUAENJH2XY4AOVGTJKPSCOXW3746PUH7QFGPBDOPPHYLIGORA"

SECRETARY_SESSION = {"id": 1837984392, "username": "itolstov"}
PLAIN_SESSION = {"id": 1863399780, "username": "attid"}


def _secretaries_mock(by_account):
    """Мок _secretaries_by_account: {адрес счёта: {telegram_id}}."""
    return patch(
        "routers.decision._secretaries_by_account",
        new=AsyncMock(return_value=by_account),
    )


def _signer_mock(account_id, telegram_id):
    """user_org_names (тест-режим): grist_cache.find_by_index возвращает юзера."""
    return patch(
        "other.grist_cache.grist_cache.find_by_index",
        return_value={
            "telegram_id": telegram_id,
            "account_id": account_id,
            "username": "itolstov",
        },
    )


def _tables_mock(**tables):
    """Мок load_table_data по таблице вместо позиционного side_effect.

    Ключи — атрибуты MTLGrist (QUESTIONS, QUESTION_DATA, QUESTION_TEMPLATES)
    и имена таблиц сид-режима (EURMTL_secretaries, EURMTL_accounts,
    EURMTL_users). Неизвестная таблица → []. Не зависит от порядка вызовов
    и горячего кеша секретарей между тестами. Орги читаются из orgs_config,
    поэтому ORGS в мок не передаётся.
    """
    from other.grist_tools import MTLGrist

    by_name = {}
    for attr, rows in tables.items():
        table = getattr(MTLGrist, attr, None)
        key = table.table_name if table is not None else attr
        by_name[key] = rows

    async def fake(table, *args, **kwargs):
        return list(by_name.get(table.table_name, []))

    return patch(
        "other.grist_tools.grist_manager.load_table_data",
        new=AsyncMock(side_effect=fake),
    )


@pytest.mark.asyncio
async def test_add_draft_creates_question_without_tg(client):
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]
        session["d2_org"] = "PFM"

    questions = [{"id": 9, "NUMBER": 76, "TITLE": "", "READING": 1}]
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        """QUESTIONS: 1-я проверка номера — 76 ещё нет, после post — появился."""
        name = table.table_name
        if name == "D2_QUESTIONS":
            calls["questions"] += 1
            return questions if calls["questions"] >= 2 else []
        return []

    with (
        _secretaries_mock({PFM_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(side_effect=fake),
        ),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
    ):
        response = await client.post(
            "/d2/add",
            form={
                "question_number": "76",
                "short_subject": "Draft topic",
                "inquiry": "<p>Draft body</p>",
                "status": "❗️ #active",
                "reading": "1",
                "as_draft": "on",
            },
        )

    assert response.status_code == 302
    assert send_mock.await_args is None  # в TG ничего не уходит
    assert post_mock.await_count == 2  # QUESTIONS + QUESTION_DATA
    data_payload = post_mock.await_args_list[-1].args[1]
    fields = data_payload["records"][0]["fields"]
    assert "TELEGRAM_LINK" not in fields  # черновик = пустой TELEGRAM_LINK
    assert "ORG" not in fields  # в D2_QUESTION_DATA нет колонки ORG (прод-схема)


@pytest.mark.asyncio
async def test_dev_stand_rejects_unknown_columns(client):
    """Дабл Grist валидирует схему: неизвестное поле = 400, как реальный Grist.

    Регрессия-2026-10-10: post ORG в D2_QUESTION_DATA падал 400 на проде,
    тесты проходили, потому что дабл принимал любые поля.
    """
    from quart import Quart

    from other.dev_stand import _TABLES, blueprint as stand
    from other.grist_tools import MTLGrist

    doc = MTLGrist.QUESTION_DATA.access_id
    table = MTLGrist.QUESTION_DATA.table_name
    _TABLES.pop(doc, None)  # чистый стенд для детерминизма
    known = {"UUID": "x", "BODY": "b", "STATUS": "❗️ #active"}
    bad = dict(known, ORG="PFM")  # колонки нет в продовой схеме

    app = Quart(__name__)
    app.register_blueprint(stand)
    test_client = app.test_client()
    ok = await test_client.post(
        f"/api/docs/{doc}/tables/{table}/records",
        json={"records": [{"fields": known}]},
    )
    assert ok.status_code == 200
    bad_resp = await test_client.post(
        f"/api/docs/{doc}/tables/{table}/records",
        json={"records": [{"fields": bad}]},
    )
    assert bad_resp.status_code == 400
    assert _TABLES[doc][table][-1]["fields"] == known  # битая запись не попала


@pytest.mark.asyncio
async def test_add_publish_still_sends_message(client):
    """Без чекбокса: sendRichMessage с блоками конвертера и ссылка."""
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]
        session["d2_org"] = "PFM"

    msg = AsyncMock()
    msg.message_id = 4242
    questions = [{"id": 9, "NUMBER": 75, "TITLE": "", "READING": 1}]
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        """QUESTIONS: 1-я проверка номера — 75 ещё нет, после post — появился."""
        name = table.table_name
        if name == "D2_QUESTIONS":
            calls["questions"] += 1
            return questions if calls["questions"] >= 2 else []
        return []

    with (
        _secretaries_mock({PFM_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(side_effect=fake),
        ),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
        patch(
            "routers.decision.skynet_bot.send_rich_message",
            new=AsyncMock(return_value=msg),
        ) as rich_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
    ):
        response = await client.post(
            "/d2/add",
            form={
                "question_number": "75",
                "short_subject": "Topic",
                "inquiry": "<p>Body</p>",
                "status": "❗️ #active",
                "reading": "1",
            },
        )

    assert response.status_code == 302
    send_mock.assert_not_awaited()  # rich прошёл — легаси не нужен
    rich_kwargs = rich_mock.await_args.kwargs
    assert rich_kwargs["chat_id"] == -1001863399780
    blocks = rich_kwargs["rich_message"]["blocks"]
    assert blocks[0] == {
        "type": "paragraph",
        "text": {"type": "bold", "text": "❗️ #active"},
    }
    assert {"type": "paragraph", "text": "Body"} in blocks
    fields = post_mock.await_args_list[-1].args[1]["records"][0]["fields"]
    # Воркспейс PFM: канал первого чтения из orgs_config.
    assert fields["TELEGRAM_LINK"] == "https://t.me/c/1863399780/4242"


@pytest.mark.asyncio
async def test_add_publish_falls_back_to_legacy_on_convert_error(client):
    """Конвертер упал → sendMessage+SULGUK (пилот не блокируем)."""
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]
        session["d2_org"] = "PFM"

    msg = AsyncMock()
    msg.message_id = 4243
    questions = [{"id": 9, "NUMBER": 75, "TITLE": "", "READING": 1}]
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        name = table.table_name
        if name == "D2_QUESTIONS":
            calls["questions"] += 1
            return questions if calls["questions"] >= 2 else []
        return []

    with (
        _secretaries_mock({PFM_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(side_effect=fake),
        ),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
        patch(
            "routers.decision.html_to_rich_message",
            side_effect=ValueError("boom"),
        ),
        patch(
            "routers.decision.skynet_bot.send_rich_message", new=AsyncMock()
        ) as rich_mock,
        patch(
            "routers.decision.skynet_bot.send_message",
            new=AsyncMock(return_value=msg),
        ) as send_mock,
    ):
        response = await client.post(
            "/d2/add",
            form={
                "question_number": "75",
                "short_subject": "Topic",
                "inquiry": "<p>Body</p>",
                "status": "❗️ #active",
                "reading": "1",
            },
        )

    assert response.status_code == 302
    rich_mock.assert_not_awaited()
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs["parse_mode"] is not None
    fields = post_mock.await_args_list[-1].args[1]["records"][0]["fields"]
    assert fields["TELEGRAM_LINK"] == "https://t.me/c/1863399780/4243"


@pytest.mark.asyncio
async def test_publish_draft_by_secretary(client):
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]

    msg = AsyncMock()
    msg.message_id = 5151
    with (
        _secretaries_mock({GORA_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
        patch(
            "routers.decision.skynet_bot.send_rich_message",
            new=AsyncMock(return_value=msg),
        ) as rich_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
        patch(
            "routers.decision.skynet_bot.edit_message_text", new=AsyncMock()
        ) as edit_mock,
    ):
        questions = [
            {
                "id": 2,
                "NUMBER": 2,
                "TITLE": "Купить сервер",
                "READING": 1,
                "ORG": "GORA",
            }
        ]
        data = [
            {
                "id": 3,
                "QUESTION_ID": 2,
                "READING": 1,
                "UUID": DRAFT_UUID,
                "TELEGRAM_LINK": "",
                "BODY": "<p>Body</p>",
                "STATUS": "✅ #done",
                "CREATED_BY": "@attid",
            }
        ]
        # /d2/publish: _find_question_row (3) + _load_question_tables (3).
        # Доступ — секретарство GORA из _secretaries_mock.
        load_mock.side_effect = [
            questions,
            data,
            [],
            questions,
            data,
            [],
        ]
        response = await client.post(f"/d2/{DRAFT_UUID}/publish")

    assert response.status_code == 302
    send_mock.assert_not_awaited()
    edit_mock.assert_not_awaited()
    rich_kwargs = rich_mock.await_args.kwargs
    assert rich_kwargs["chat_id"] == -10084131737
    assert rich_kwargs["rich_message"]["blocks"] == [
        {"type": "paragraph", "text": {"type": "bold", "text": "✅ #done"}},
        {"type": "paragraph", "text": "Body"},
    ]
    patched = patch_mock.await_args.args[1]
    # GORA: канал орги вопроса из orgs_config (один канал на все чтения).
    assert patched["records"][0]["fields"]["TELEGRAM_LINK"] == (
        "https://t.me/c/84131737/5151"
    )


@pytest.mark.asyncio
async def test_republish_dead_post_sends_new_message(client):
    """edit(rich) по мёртвому посту → sendRichMessage + новая ссылка."""
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]

    msg = AsyncMock()
    msg.message_id = 6000
    with (
        _secretaries_mock({PFM_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
        patch(
            "routers.decision.skynet_bot.send_rich_message",
            new=AsyncMock(return_value=msg),
        ) as rich_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
        patch(
            "routers.decision.skynet_bot.edit_message_text",
            new=AsyncMock(
                side_effect=Exception("Bad Request: message to edit not found")
            ),
        ) as edit_mock,
    ):
        questions = [
            {"id": 1, "NUMBER": 1, "TITLE": "Принять отчёт", "READING": 1, "ORG": "PFM"}
        ]
        data = [
            {
                "id": 1,
                "QUESTION_ID": 1,
                "READING": 1,
                "UUID": PUBLISHED_UUID,
                "TELEGRAM_LINK": "https://t.me/c/1837984392/100",
                "BODY": "<p>Body</p>",
                "STATUS": "❗️ #active",
                "CREATED_BY": "@itolstov",
            }
        ]
        # /d2/publish: кеш таблиц делает число лоадов неважным —
        # мок по имени таблицы (как в _tables_mock).
        async def fake_load(table, *a, **k):
            return {
                "D2_QUESTIONS": questions,
                "D2_QUESTION_DATA": data,
            }.get(table.table_name, [])

        load_mock.side_effect = fake_load
        response = await client.post(f"/d2/{PUBLISHED_UUID}/publish")

    assert response.status_code == 302
    edit_mock.assert_awaited_once()
    assert edit_mock.await_args.kwargs["message_id"] == 100
    assert send_mock.assert_not_awaited() is None
    assert rich_mock.await_args.kwargs["rich_message"]["blocks"] == [
        {"type": "paragraph", "text": {"type": "bold", "text": "❗️ #active"}},
        {"type": "paragraph", "text": "Body"},
    ]
    patched = patch_mock.await_args.args[1]
    # PFM: канал первого чтения орги вопроса из orgs_config.
    assert patched["records"][0]["fields"]["TELEGRAM_LINK"] == (
        "https://t.me/c/1863399780/6000"
    )


@pytest.mark.asyncio
async def test_republish_dead_post_falls_back_to_legacy(client):
    """sendRichMessage тоже упал → sendMessage+SULGUK как финальный фолбэк."""
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]

    msg = AsyncMock()
    msg.message_id = 6001
    with (
        _secretaries_mock({PFM_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
        patch(
            "routers.decision.skynet_bot.send_rich_message",
            new=AsyncMock(side_effect=Exception("Bad Request: chat not found")),
        ),
        patch(
            "routers.decision.skynet_bot.send_message",
            new=AsyncMock(return_value=msg),
        ) as send_mock,
        patch(
            "routers.decision.skynet_bot.edit_message_text",
            new=AsyncMock(
                side_effect=Exception("Bad Request: message to edit not found")
            ),
        ),
    ):
        questions = [
            {"id": 1, "NUMBER": 1, "TITLE": "Принять отчёт", "READING": 1, "ORG": "PFM"}
        ]
        data = [
            {
                "id": 1,
                "QUESTION_ID": 1,
                "READING": 1,
                "UUID": PUBLISHED_UUID,
                "TELEGRAM_LINK": "https://t.me/c/1837984392/100",
                "BODY": "<p>Body</p>",
                "STATUS": "❗️ #active",
                "CREATED_BY": "@itolstov",
            }
        ]
        load_mock.side_effect = [questions, data, [], questions, data, []]
        response = await client.post(f"/d2/{PUBLISHED_UUID}/publish")

    assert response.status_code == 302
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs["parse_mode"] is not None
    patched = patch_mock.await_args.args[1]
    assert patched["records"][0]["fields"]["TELEGRAM_LINK"] == (
        "https://t.me/c/1863399780/6001"
    )


@pytest.mark.asyncio
async def test_publish_by_non_secretary_rejected(client):
    """Подписант PFM (не секретарь) публиковать не может."""
    async with client.session_transaction() as session:
        session["userdata"] = PLAIN_SESSION
        session["user_id"] = PLAIN_SESSION["id"]

    with (
        _secretaries_mock({GORA_ADDRESS: {1837984392}}),
        _signer_mock(PFM_ADDRESS, 1863399780),  # attid подписант PFM
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
    ):
        questions = [
            {"id": 2, "NUMBER": 2, "TITLE": "Купить сервер", "READING": 1, "ORG": "PFM"}
        ]
        data = [
            {
                "id": 3,
                "QUESTION_ID": 2,
                "READING": 1,
                "UUID": DRAFT_UUID,
                "TELEGRAM_LINK": "",
                "BODY": "<p>Body</p>",
                "STATUS": "✅ #done",
                "CREATED_BY": "@attid",
            }
        ]
        load_mock.side_effect = [questions, data, [], questions, data, []]
        response = await client.post(f"/d2/{DRAFT_UUID}/publish")

    assert response.status_code == 302
    send_mock.assert_not_awaited()
    async with client.session_transaction() as session:
        flashes = dict(session.get("_flashes", []))
    assert any("только секретари" in str(m) for m in flashes.values())


@pytest.mark.asyncio
async def test_question_screen_hides_publish_button_for_draft_non_secretary(client):
    async with client.session_transaction() as session:
        session["userdata"] = PLAIN_SESSION
        session["user_id"] = PLAIN_SESSION["id"]

    with (
        _secretaries_mock({GORA_ADDRESS: {1837984392}}),
        _signer_mock(PFM_ADDRESS, 1863399780),  # attid подписант PFM
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
    ):
        questions = [
            {"id": 2, "NUMBER": 2, "TITLE": "Купить сервер", "READING": 1, "ORG": "PFM"}
        ]
        data = [
            {
                "id": 3,
                "QUESTION_ID": 2,
                "READING": 1,
                "UUID": DRAFT_UUID,
                "TELEGRAM_LINK": "",
                "BODY": "<p>Body</p>",
                "STATUS": "✅ #done",
                "CREATED_BY": "@attid",
            }
        ]
        load_mock.side_effect = [questions, data, [], questions, data, []]
        response = await client.get(f"/d2/{DRAFT_UUID}")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "/publish" not in body


@pytest.mark.asyncio
async def test_question_screen_shows_publish_button_for_secretary_draft(client):
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]

    with (
        _secretaries_mock({GORA_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
    ):
        questions = [
            {
                "id": 2,
                "NUMBER": 2,
                "TITLE": "Купить сервер",
                "READING": 1,
                "ORG": "GORA",
            }
        ]
        data = [
            {
                "id": 3,
                "QUESTION_ID": 2,
                "READING": 1,
                "UUID": DRAFT_UUID,
                "TELEGRAM_LINK": "",
                "BODY": "<p>Body</p>",
                "STATUS": "✅ #done",
                "CREATED_BY": "@attid",
            }
        ]
        # GET /d2/<uuid>: _find_question_row (3 loads: QUESTIONS, DATA,
        # TEMPLATES) + _load_question_tables (3). Доступ — секретарство
        # GORA из _secretaries_mock.
        load_mock.side_effect = [
            questions,
            data,
            [],
            questions,
            data,
            [],
        ]
        response = await client.get(f"/d2/{DRAFT_UUID}")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert f"/d2/{DRAFT_UUID}/publish" in body
    assert "черновик" in body


@pytest.mark.asyncio
async def test_edit_list_marks_draft_questions(client):
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]
        session["d2_org"] = "PFM"

    questions = [
        {"id": 1, "NUMBER": 1, "TITLE": "Published", "ORG": "PFM"},
        {"id": 2, "NUMBER": 2, "TITLE": "Draft", "ORG": "PFM"},
    ]
    question_data = [
        {
            "QUESTION_ID": 1,
            "READING": "1",
            "STATUS": "❗️ #active",
            "UUID": "u1",
            "TELEGRAM_LINK": "https://t.me/c/1/100",
        },
        {
            "QUESTION_ID": 2,
            "READING": "1",
            "STATUS": "❗️ #active",
            "UUID": "u2",
            "TELEGRAM_LINK": "",
        },
    ]

    with (
        _secretaries_mock({PFM_ADDRESS: {1837984392}}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(
                side_effect=[
                    questions,
                    question_data,
                ]
            ),
        ),
    ):
        response = await client.get("/d2/fragment/edit?status=all")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "черновик" in body

@pytest.fixture(autouse=True)
def _clear_question_tables_cache():
    """Кеш D2_* таблиц (TTL 5с) переживает тесты — чистим как остальные кеши."""
    from routers.decision import question_tables_cache
    question_tables_cache.cache.clear()
    yield
    question_tables_cache.cache.clear()


@pytest.mark.asyncio
async def test_add_same_number_other_org_links_correct_question(client):
    """Регрессия-2026-10-10: №1 уже есть в MTLA, создаём №1 в GORA —
    чтение должно прицепиться к GORA-вопросу, не к первому №1 в таблице.
    Баг: question_id искался по номеру без орга — GORA-чтение прицепилось
    к MTLA №1 и публикавало в канал MTLA."""
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]
        session["d2_org"] = "GORA"

    questions = [
        {"id": 154, "NUMBER": 1, "TITLE": "MTLA q", "READING": 3, "ORG": "MTLA"},
    ]
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        name = table.table_name
        if name == "D2_QUESTIONS":
            calls["questions"] += 1
            # 1-й вызов — дубликат-чек (GORA №1 нет), 2-й — поиск id после
            # POST: GORA №1 уже создан.
            if calls["questions"] >= 2:
                return questions + [
                    {"id": 200, "NUMBER": 1, "TITLE": "GORA q", "READING": 1, "ORG": "GORA"}
                ]
            return questions
        return []

    with (
        _secretaries_mock({GORA_ADDRESS: {1837984392}}),
        _signer_mock(GORA_ADDRESS, 1837984392),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(side_effect=fake),
        ),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()),
    ):
        response = await client.post(
            "/d2/add",
            form={
                "question_number": "1",
                "short_subject": "GORA question",
                "inquiry": "<p>Body</p>",
                "status": "❗️ #active",
                "reading": "1",
                "as_draft": "on",
            },
        )

    assert response.status_code == 302
    data_payload = post_mock.await_args_list[-1].args[1]
    fields = data_payload["records"][0]["fields"]
    assert fields["QUESTION_ID"] == 200  # GORA-вопрос, не MTLA id=154
