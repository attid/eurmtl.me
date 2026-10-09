"""D2: черновики и публикация/републикация вопросов."""

import pytest
from unittest.mock import AsyncMock, patch

DRAFT_UUID = "aaaabbbbccccddddeeeeffff00003333"  # вопрос №2, TELEGRAM_LINK=""
PUBLISHED_UUID = "aaaabbbbccccddddeeeeffff00001111"  # вопрос №1, чтение 1

# Реальный адрес PFM из orgs_config (секретарь стенда — подписант).
PFM_ADDRESS = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"

SECRETARY_SESSION = {"id": 1837984392, "username": "itolstov"}
PLAIN_SESSION = {"id": 1863399780, "username": "attid"}


def _secretary_ids_mock(ids):
    return patch(
        "routers.decision._load_secretary_telegram_ids",
        new=AsyncMock(return_value=ids),
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

    questions = [{"id": 9, "NUMBER": 76, "TITLE": "", "READING": 1}]
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        """QUESTIONS: 1-я проверка номера — 76 ещё нет, после post — появился."""
        name = table.table_name
        if name == "QUESTIONS":
            calls["questions"] += 1
            return questions if calls["questions"] >= 2 else []
        seeded = {
            "Secretaries": [{"id": 1, "account": 1, "users": [1]}],
            "Accounts": [
                {"id": 1, "account": PFM_ADDRESS},
            ],
            "Users": [
                {
                    "id": 1,
                    "telegram_id": 1837984392,
                    "account_id": PFM_ADDRESS,
                }
            ],
        }
        return list(seeded.get(name, []))

    with (
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
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


@pytest.mark.asyncio
async def test_add_publish_still_sends_message(client):
    """Без чекбокса поведение прежнее: send_message и ссылка."""
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]

    msg = AsyncMock()
    msg.message_id = 4242
    questions = [{"id": 9, "NUMBER": 75, "TITLE": "", "READING": 1}]
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        """QUESTIONS: 1-я проверка номера — 75 ещё нет, после post — появился."""
        name = table.table_name
        if name == "QUESTIONS":
            calls["questions"] += 1
            return questions if calls["questions"] >= 2 else []
        seeded = {
            "Secretaries": [{"id": 1, "account": 1, "users": [1]}],
            "Accounts": [
                {"id": 1, "account": PFM_ADDRESS},
            ],
            "Users": [
                {
                    "id": 1,
                    "telegram_id": 1837984392,
                    "account_id": PFM_ADDRESS,
                }
            ],
        }
        return list(seeded.get(name, []))

    with (
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(side_effect=fake),
        ),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
        patch(
            "routers.decision.skynet_bot.send_message", new=AsyncMock(return_value=msg)
        ),
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
    fields = post_mock.await_args_list[-1].args[1]["records"][0]["fields"]
    # Дефолтная орга — PFM: канал первого чтения из orgs_config.
    assert fields["TELEGRAM_LINK"] == "https://t.me/c/1863399780/4242"


@pytest.mark.asyncio
async def test_publish_draft_by_secretary(client):
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]

    msg = AsyncMock()
    msg.message_id = 5151
    with (
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
        _secretary_ids_mock({1837984392}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
        patch(
            "routers.decision.skynet_bot.send_message", new=AsyncMock(return_value=msg)
        ) as send_mock,
        patch(
            "routers.decision.skynet_bot.edit_message_text", new=AsyncMock()
        ) as edit_mock,
    ):
        questions = [{"id": 2, "NUMBER": 2, "TITLE": "Купить сервер", "READING": 1}]
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
        # Видимость секретарю — из orgs_config, Grist не читается.
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
    assert send_mock.await_count == 1
    edit_mock.assert_not_awaited()
    patched = patch_mock.await_args.args[1]
    assert patched["records"][0]["fields"]["TELEGRAM_LINK"] == (
        "https://t.me/c/1837984392/5151"
    )


@pytest.mark.asyncio
async def test_republish_dead_post_sends_new_message(client):
    """edit_message_text по мёртвому посту → send_message + новая ссылка."""
    async with client.session_transaction() as session:
        session["userdata"] = SECRETARY_SESSION
        session["user_id"] = SECRETARY_SESSION["id"]

    msg = AsyncMock()
    msg.message_id = 6000
    with (
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
        _secretary_ids_mock({1837984392}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
        patch(
            "routers.decision.skynet_bot.send_message", new=AsyncMock(return_value=msg)
        ) as send_mock,
        patch(
            "routers.decision.skynet_bot.edit_message_text",
            new=AsyncMock(
                side_effect=Exception("Bad Request: message to edit not found")
            ),
        ) as edit_mock,
    ):
        questions = [{"id": 1, "NUMBER": 1, "TITLE": "Принять отчёт", "READING": 1}]
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
        # /d2/publish: _find_question_row (3) + _load_question_tables (3).
        # Видимость секретарю — из orgs_config, Grist не читается.
        load_mock.side_effect = [
            questions,
            data,
            [],
            questions,
            data,
            [],
        ]
        response = await client.post(f"/d2/{PUBLISHED_UUID}/publish")

    assert response.status_code == 302
    edit_mock.assert_awaited_once()
    assert edit_mock.await_args.kwargs["message_id"] == "100"
    assert send_mock.await_count == 1
    patched = patch_mock.await_args.args[1]
    assert patched["records"][0]["fields"]["TELEGRAM_LINK"] == (
        "https://t.me/c/1837984392/6000"
    )


@pytest.mark.asyncio
async def test_publish_by_non_secretary_rejected(client):
    async with client.session_transaction() as session:
        session["userdata"] = PLAIN_SESSION
        session["user_id"] = PLAIN_SESSION["id"]

    with (
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
        _secretary_ids_mock(set()),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
    ):
        questions = [{"id": 2, "NUMBER": 2, "TITLE": "Купить сервер", "READING": 1}]
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
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
        _secretary_ids_mock(set()),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
    ):
        questions = [{"id": 2, "NUMBER": 2, "TITLE": "Купить сервер", "READING": 1}]
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
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
        _secretary_ids_mock({1837984392}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=[]),
        ) as load_mock,
    ):
        questions = [{"id": 2, "NUMBER": 2, "TITLE": "Купить сервер", "READING": 1}]
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
        # TEMPLATES) + _load_question_tables (3). Видимость секретарю —
        # из orgs_config, Grist не читается.
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

    questions = [
        {"id": 1, "NUMBER": 1, "TITLE": "Published"},
        {"id": 2, "NUMBER": 2, "TITLE": "Draft"},
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
        _secretary_ids_mock({1837984392}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            # /d2/fragment/edit: QUESTIONS, QUESTION_DATA. Список фильтра
            # берётся из orgs_config (PFM/GORA/USDMM/TFM) без Grist.
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
