"""MCP-эндпоинт: Bearer-аутентификация, JSON-RPC, tools d2."""

import contextlib
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from routers.token import create_token

SECRETARY = {"id": 1837984392, "username": "itolstov"}
PLAIN = {"id": 1863399780, "username": "attid"}

PFM_ADDRESS = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"


@pytest.fixture(autouse=True)
def _clear_org_caches():
    """Кеши видимости переживают тесты (TTL 60с+) — чистим, как в
    test_d2_workspace.py, иначе чужой прогон может подсадить видимость."""
    from other.grist_tools import org_signers_cache
    from routers.decision import question_tables_cache, secretary_ids_cache

    org_signers_cache.cache.clear()
    secretary_ids_cache.cache.clear()
    question_tables_cache.cache.clear()
    yield
    org_signers_cache.cache.clear()
    secretary_ids_cache.cache.clear()
    question_tables_cache.cache.clear()


QUESTIONS = [
    {"id": 1, "NUMBER": 1, "TITLE": "Вопрос один", "READING": 1, "ORG": "PFM"},
    {"id": 2, "NUMBER": 2, "TITLE": "Черновик", "READING": 1, "ORG": "PFM"},
]
QUESTION_DATA = [
    {
        "id": 11,
        "QUESTION_ID": 1,
        "READING": 1,
        "UUID": "pub-uuid-0001",
        "BODY": "<p>текст</p>",
        "EXTRA": "",
        "STATUS": "❗️ #active",
        "CREATED_BY": "@itolstov",
        "CREATED_AT": "2026-11-01T10:00:00",
        "TELEGRAM_LINK": "https://t.me/c/123/456",
    },
    {
        "id": 12,
        "QUESTION_ID": 2,
        "READING": 1,
        "UUID": "draft-uuid-002",
        "BODY": "<p>черновик</p>",
        "EXTRA": "",
        "STATUS": "❗️ #active",
        "CREATED_BY": "@itolstov",
        "CREATED_AT": "2026-11-02T10:00:00",
    },
]


def _signer_mock(account_id, telegram_id):
    return patch(
        "other.grist_cache.grist_cache.find_by_index",
        return_value={
            "telegram_id": telegram_id,
            "account_id": account_id,
            "username": "itolstov",
        },
    )


def _tables_mock(questions=QUESTIONS, question_data=QUESTION_DATA):
    """Моки с состоянием: post_data дописывает строки (как живой Grist),
    поэтому create_draft находит созданный QUESTION_ID после инвалидации кеша."""
    from other.grist_tools import MTLGrist

    state = {
        MTLGrist.QUESTIONS.table_name: list(questions),
        MTLGrist.QUESTION_DATA.table_name: list(question_data),
    }

    async def fake_load(table, *args, **kwargs):
        return list(state.get(table.table_name, []))

    async def fake_post(table, payload, *args, **kwargs):
        for record in payload.get("records", []):
            fields = dict(record.get("fields", {}))
            fields["id"] = (
                max((r.get("id", 0) for r in state[table.table_name]), default=0) + 1
            )
            state[table.table_name].append(fields)

    async def fake_patch(table, payload, *args, **kwargs):
        by_id = {r.get("id"): r for r in state[table.table_name]}
        for record in payload.get("records", []):
            row = by_id.get(record.get("id"))
            if row is not None:
                row.update(record.get("fields", {}))

    load_patch = patch(
        "other.grist_tools.grist_manager.load_table_data",
        new=AsyncMock(side_effect=fake_load),
    )
    post_patch = patch(
        "other.grist_tools.grist_manager.post_data",
        new=AsyncMock(side_effect=fake_post),
    )
    patch_data_patch = patch(
        "other.grist_tools.grist_manager.patch_data",
        new=AsyncMock(side_effect=fake_patch),
    )
    return load_patch, post_patch, patch_data_patch


def _rpc(method, params=None, req_id=1):
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def _auth(raw_token):
    return {"Authorization": f"Bearer {raw_token}"}


@pytest_asyncio.fixture
async def secretary_token(db_pool):
    async with db_pool() as session:
        return await create_token(session, SECRETARY["id"], "itolstov", "d2")


@pytest_asyncio.fixture
async def plain_token(db_pool):
    async with db_pool() as session:
        return await create_token(session, PLAIN["id"], "attid", "d2")


def _secretary_mocks():
    """Секретарь PFM (по счёту MAIN_ADDRESS) + таблицы."""

    signer = _signer_mock(PFM_ADDRESS, SECRETARY["id"])
    secretary = patch(
        "routers.decision._secretaries_by_account",
        new=AsyncMock(return_value={PFM_ADDRESS: {SECRETARY["id"]}}),
    )
    mcp_secretary = patch(
        "routers.decision._org_secretary_addresses",
        new=AsyncMock(return_value={SECRETARY["id"]}),
    )
    tables = _tables_mock()
    return signer, secretary, mcp_secretary, tables


@pytest.mark.asyncio
async def test_mcp_requires_bearer(client):
    response = await client.post("/mcp", json=_rpc("initialize"))
    assert response.status_code == 401

    response = await client.post(
        "/mcp", json=_rpc("initialize"), headers=_auth("wrong-token")
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mcp_initialize_and_tools_list(client, secretary_token):
    response = await client.post(
        "/mcp", json=_rpc("initialize"), headers=_auth(secretary_token)
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["result"]["serverInfo"]["name"] == "eurmtl-me"

    response = await client.post(
        "/mcp", json=_rpc("tools/list"), headers=_auth(secretary_token)
    )
    data = await response.get_json()
    names = {t["name"] for t in data["result"]["tools"]}
    assert names == {
        "d2_list_orgs",
        "d2_list_questions",
        "d2_get_question",
        "d2_create_draft",
        "d2_update_draft",
    }


@pytest.mark.asyncio
async def test_mcp_unknown_method(client, secretary_token):
    response = await client.post(
        "/mcp", json=_rpc("no/such/method"), headers=_auth(secretary_token)
    )
    data = await response.get_json()
    assert data["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_list_orgs(client, secretary_token):
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc("tools/call", {"name": "d2_list_orgs", "arguments": {}}),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    result = json.loads(data["result"]["content"][0]["text"])
    assert any(o["name"] == "PFM" and o["can_edit"] for o in result["orgs"])


@pytest.mark.asyncio
async def test_mcp_list_questions_draft_visible(client, secretary_token):
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "d2_list_questions", "arguments": {"org": "PFM"}},
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    result = json.loads(data["result"]["content"][0]["text"])
    by_number = {q["number"]: q for q in result["questions"]}
    assert by_number[1]["is_draft"] is False
    assert by_number[2]["is_draft"] is True


@pytest.mark.asyncio
async def test_mcp_foreign_org_rejected(client, plain_token):
    """attid не подписант и не секретарь PFM — org недоступна."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "d2_list_questions", "arguments": {"org": "PFM"}},
            ),
            headers=_auth(plain_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "недоступна" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_create_draft_writes_grist(client, secretary_token):
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, post_patch as post_mock:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_create_draft",
                    "arguments": {
                        "org": "PFM",
                        "title": "Новый вопрос",
                        "body": "<p>Предложение</p>",
                    },
                },
            ),
            headers=_auth(secretary_token),
        )
        posted = list(post_mock.call_args_list)
    data = await response.get_json()
    result = json.loads(data["result"]["content"][0]["text"])
    assert result["number"] == 3  # авто max+1
    assert result["uuid"]

    from other.grist_tools import MTLGrist

    questions_call = next(c for c in posted if c.args[0] == MTLGrist.QUESTIONS)
    fields = questions_call.args[1]["records"][0]["fields"]
    assert fields["NUMBER"] == 3
    assert fields["TITLE"] == "Новый вопрос"
    assert fields["ORG"] == "PFM"
    data_call = next(c for c in posted if c.args[0] == MTLGrist.QUESTION_DATA)
    dfields = data_call.args[1]["records"][0]["fields"]
    assert dfields["CREATED_BY"] == "@itolstov"
    assert "TELEGRAM_LINK" not in dfields  # черновик: без TG


@pytest.mark.asyncio
async def test_mcp_create_draft_duplicate_number(client, secretary_token):
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, post_patch, patch_data_patch:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_create_draft",
                    "arguments": {
                        "org": "PFM",
                        "title": "Дубль",
                        "body": "<p>х</p>",
                        "number": 1,
                    },
                },
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "занят" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_update_draft_patches_body(client, secretary_token):
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, patch_data_patch as patch_mock:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_update_draft",
                    "arguments": {
                        "uuid": "draft-uuid-002",
                        "body": "<p>правка</p>",
                        "title": "Обновлённый",
                    },
                },
            ),
            headers=_auth(secretary_token),
        )
        patched = list(patch_mock.call_args_list)
    data = await response.get_json()
    result = json.loads(data["result"]["content"][0]["text"])
    assert "BODY" in result["updated"]

    from other.grist_tools import MTLGrist

    body_call = next(c for c in patched if c.args[0] == MTLGrist.QUESTION_DATA)
    assert body_call.args[1]["records"][0]["fields"]["BODY"] == "<p>правка</p>"
    title_call = next(c for c in patched if c.args[0] == MTLGrist.QUESTIONS)
    assert title_call.args[1]["records"][0]["fields"]["TITLE"] == "Обновлённый"


@pytest.mark.asyncio
async def test_mcp_update_published_reading_rejected(client, secretary_token):
    """Опубликованное чтение (TELEGRAM_LINK есть) MCP не правит."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, post_patch, patch_data_patch:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "d2_update_draft", "arguments": {"uuid": "pub-uuid-0001"}},
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "опубликованное" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_get_question_returns_all_readings(client, secretary_token):
    """У вопроса с 2 чтениями get_question возвращает оба (баг круга 1:
    фильтр по uuid срезал до одного чтения)."""
    two_readings = QUESTION_DATA + [
        {
            "id": 13,
            "QUESTION_ID": 1,
            "READING": 2,
            "UUID": "draft-uuid-001-r2",
            "BODY": "<p>чтение 2</p>",
            "EXTRA": "",
            "STATUS": "☑️ #next",
            "CREATED_BY": "@itolstov",
            "CREATED_AT": "2026-11-03T10:00:00",
        }
    ]
    signer, secretary, mcp_secretary, _ = _secretary_mocks()
    tables = _tables_mock(question_data=two_readings)
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "d2_get_question", "arguments": {"uuid": "draft-uuid-001-r2"}},
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    result = json.loads(data["result"]["content"][0]["text"])
    readings = result["readings"]
    assert [r["reading"] for r in readings] == [1, 2]
    assert readings[0]["uuid"] == "pub-uuid-0001"
    assert readings[0]["is_draft"] is False
    assert readings[1]["is_draft"] is True


@pytest.mark.asyncio
async def test_mcp_get_question_foreign_org_rejected(client, plain_token):
    signer, _secretary, _mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, _secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "d2_get_question", "arguments": {"uuid": "pub-uuid-0001"}},
            ),
            headers=_auth(plain_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    # Существование чужого вопроса не палим (decision.py:565) — «не найден».
    assert "не найден" in data["result"]["content"][0]["text"]
    assert "недоступна" not in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_create_draft_bad_number_rejected(client, secretary_token):
    """Нечисловые number/reading — ToolError, не 500."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, post_patch, patch_data_patch:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_create_draft",
                    "arguments": {"org": "PFM", "title": "х", "number": "abc"},
                },
            ),
            headers=_auth(secretary_token),
        )
        assert (await response.get_json())["result"]["isError"] is True

        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_create_draft",
                    "arguments": {"org": "PFM", "title": "х", "reading": "abc"},
                },
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True


@pytest.mark.asyncio
async def test_mcp_update_draft_empty_title_rejected(client, secretary_token):
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, patch_data_patch:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_update_draft",
                    "arguments": {"uuid": "draft-uuid-002", "title": "  "},
                },
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "title" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_params_null_and_rpc_error(client, secretary_token):
    """params=null не роняет логирование; битый JSON и unknown tool — ошибки RPC."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        # "params": null — после обработки 200 (раньше падал логгер).
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": None},
            headers=_auth(secretary_token),
        )
        assert response.status_code == 200
        assert "tools" in (await response.get_json())["result"]

        response = await client.post(
            "/mcp",
            data=b"{not json",
            headers={**_auth(secretary_token), "Content-Type": "application/json"},
        )
        assert (await response.get_json())["error"]["code"] == -32700

        response = await client.post(
            "/mcp",
            json={"jsonrpc": "1.0", "id": 1, "method": "initialize"},
            headers=_auth(secretary_token),
        )
        assert (await response.get_json())["error"]["code"] == -32600

        response = await client.post(
            "/mcp",
            json=_rpc("tools/call", {"name": "unknown_tool", "arguments": {}}),
            headers=_auth(secretary_token),
        )
        assert (await response.get_json())["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_mcp_params_nondict_rejected(client, secretary_token):
    """params:"string"/[1,2] и arguments:"str" — -32602, не 500."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        for bad_params in ("not-dict", [1, 2]):
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": bad_params,
                },
                headers=_auth(secretary_token),
            )
            assert (await response.get_json())["error"]["code"] == -32602

        response = await client.post(
            "/mcp",
            json=_rpc("tools/call", {"name": "d2_list_orgs", "arguments": "bad"}),
            headers=_auth(secretary_token),
        )
        assert (await response.get_json())["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_mcp_list_questions_skips_broken_qid(client, secretary_token):
    """Пустые/битые QUESTION_ID в QUESTION_DATA не роняют list_questions."""
    broken = QUESTION_DATA + [
        {"id": 14, "QUESTION_ID": "", "UUID": "x1", "READING": 1},
        {"id": 15, "QUESTION_ID": None, "UUID": "x2", "READING": 1},
    ]
    signer, secretary, mcp_secretary, _ = _secretary_mocks()
    tables = _tables_mock(question_data=broken)
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call", {"name": "d2_list_questions", "arguments": {"org": "PFM"}}
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert "isError" not in data["result"]
    assert len(json.loads(data["result"]["content"][0]["text"])["questions"]) == 2


@pytest.mark.asyncio
async def test_mcp_update_draft_bad_status_rejected(client, secretary_token):
    """status вне списка (например 'active' без эмодзи) — ToolError со списком."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, patch_data_patch:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_update_draft",
                    "arguments": {"uuid": "draft-uuid-002", "status": "active"},
                },
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "#active" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_update_draft_null_fields_ignored(client, secretary_token):
    """title/body/status: null — не превращаются в строку "None" (круг 3)."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, patch_data_patch as patch_mock:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_update_draft",
                    "arguments": {
                        "uuid": "draft-uuid-002",
                        "title": None,
                        "body": None,
                        "status": None,
                    },
                },
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert "isError" not in data["result"]
    # Ничего не патчилось: null-поля игнорируются, а не пишут "None".
    patch_mock.assert_not_called()
    body = json.loads(data["result"]["content"][0]["text"])
    assert body["updated"] == []


@pytest.mark.asyncio
async def test_mcp_create_draft_bad_number_and_reading(client, secretary_token):
    """number<1, reading=0 и reading больше max — ToolError, не Grist."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    for bad_args in (
        {"number": 0},
        {"number": -1},
        {"reading": 0},
        {"reading": 99},
    ):
        with signer, secretary, mcp_secretary, load_patch, post_patch:
            response = await client.post(
                "/mcp",
                json=_rpc(
                    "tools/call",
                    {
                        "name": "d2_create_draft",
                        "arguments": {"org": "PFM", "title": "x", **bad_args},
                    },
                ),
                headers=_auth(secretary_token),
            )
        data = await response.get_json()
        assert data["result"]["isError"] is True, bad_args


@pytest.mark.asyncio
async def test_mcp_empty_uuid_rejected(client, secretary_token):
    """uuid="" или отсутствует — ToolError, а не поиск по пустой строке."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, patch_data_patch:
        for args in ({"uuid": ""}, {}, {"uuid": "   "}):
            response = await client.post(
                "/mcp",
                json=_rpc(
                    "tools/call",
                    {"name": "d2_get_question", "arguments": args},
                ),
                headers=_auth(secretary_token),
            )
            data = await response.get_json()
            assert data["result"]["isError"] is True, args
            assert "uuid" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_create_draft_foreign_org_rejected(client, plain_token):
    """plain (подписант PFM) не может создать черновик в PFM — изоляция записи."""
    signer, _secretary, _mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, load_patch, post_patch:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_create_draft",
                    "arguments": {"org": "PFM", "title": "чужое"},
                },
            ),
            headers=_auth(plain_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "недоступна" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_list_questions_mixed_number_types(client, secretary_token):
    """Смешанные int/str NUMBER в Grist не роняют сортировку (круг 3)."""
    mixed = [
        {"id": 1, "NUMBER": 1, "TITLE": "int", "READING": 1, "ORG": "PFM"},
        {"id": 2, "NUMBER": "2", "TITLE": "str", "READING": 1, "ORG": "PFM"},
    ]
    signer, secretary, mcp_secretary, _ = _secretary_mocks()
    tables = _tables_mock(questions=mixed)
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call", {"name": "d2_list_questions", "arguments": {"org": "PFM"}}
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert "isError" not in data["result"]
    numbers = [
        q["number"]
        for q in json.loads(data["result"]["content"][0]["text"])["questions"]
    ]
    assert numbers == [1, "2"]


@pytest.mark.asyncio
async def test_mcp_token_other_scope_rejected(client, db_pool):
    """Токен со scope 'other' не проходит по гранулу d2 — -32602."""
    async with db_pool() as session:
        raw = await create_token(session, SECRETARY["id"], "itolstov", "other")

    response = await client.post(
        "/mcp",
        json=_rpc("tools/call", {"name": "d2_list_orgs", "arguments": {}}),
        headers=_auth(raw),
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data["error"]["code"] == -32602
    assert "scope" in data["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_create_draft_string_number_duplicate_rejected(
    client, secretary_token
):
    """NUMBER в Grist строкой "1", клиент шлёт number: 1 → «уже занят»."""
    str_number = [
        {"id": 1, "NUMBER": "1", "TITLE": "int", "READING": 1, "ORG": "PFM"},
    ]
    signer, secretary, mcp_secretary, _ = _secretary_mocks()
    tables = _tables_mock(questions=str_number)
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_create_draft",
                    "arguments": {"org": "PFM", "title": "x", "number": 1},
                },
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "уже занят" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_list_questions_reading_zero_kept(client, secretary_token):
    """READING == 0 (валидное) не фильтруется как falsy (круг 4)."""
    zero_q = [{"id": 1, "NUMBER": 1, "TITLE": "t", "READING": 1, "ORG": "PFM"}]
    zero_data = [
        {
            "id": 11,
            "QUESTION_ID": 1,
            "READING": 0,
            "UUID": "zero-uuid",
            "BODY": "<p>b</p>",
            "EXTRA": "",
            "STATUS": "❗️ #active",
            "CREATED_BY": "@itolstov",
            "CREATED_AT": "2026-11-01T10:00:00",
            "TELEGRAM_LINK": "https://t.me/c/123/456",
        },
    ]
    signer, secretary, mcp_secretary, _ = _secretary_mocks()
    tables = _tables_mock(questions=zero_q, question_data=zero_data)
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call", {"name": "d2_list_questions", "arguments": {"org": "PFM"}}
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    questions = json.loads(data["result"]["content"][0]["text"])["questions"]
    assert questions[0]["uuid"] == "zero-uuid"
    assert questions[0]["readings"] == [0]


@pytest.mark.asyncio
async def test_mcp_string_question_id_lookup(client, secretary_token):
    """QUESTION_ID строкой "1" при q.id=1 — get_question и update_draft находят."""
    str_qid = [
        {
            "id": 11,
            "QUESTION_ID": "2",
            "READING": 1,
            "UUID": "draft-uuid-002",
            "BODY": "<p>черновик</p>",
            "EXTRA": "",
            "STATUS": "❗️ #active",
            "CREATED_BY": "@itolstov",
            "CREATED_AT": "2026-11-02T10:00:00",
        },
    ]
    signer, secretary, mcp_secretary, _ = _secretary_mocks()
    tables = _tables_mock(question_data=str_qid)
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "d2_get_question", "arguments": {"uuid": "draft-uuid-002"}},
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert "isError" not in data["result"]
    body = json.loads(data["result"]["content"][0]["text"])
    assert body["number"] == 2


@pytest.mark.asyncio
async def test_mcp_update_draft_status_applied(client, secretary_token):
    """Валидный статус '☑️ #next' реально патчится (круг 4)."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, patch_data_patch as patch_mock:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {
                    "name": "d2_update_draft",
                    "arguments": {"uuid": "draft-uuid-002", "status": "☑️ #next"},
                },
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert "isError" not in data["result"]
    body = json.loads(data["result"]["content"][0]["text"])
    assert body["updated"] == ["STATUS"]
    (name, payload), _kwargs = patch_mock.call_args
    assert payload["records"][0]["fields"]["STATUS"] == "☑️ #next"


@pytest.mark.asyncio
async def test_mcp_update_draft_unknown_uuid(client, secretary_token):
    """Несуществующий uuid → isError «не найдено»."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    load_patch, post_patch, patch_data_patch = tables
    with signer, secretary, mcp_secretary, load_patch, patch_data_patch:
        response = await client.post(
            "/mcp",
            json=_rpc(
                "tools/call",
                {"name": "d2_update_draft", "arguments": {"uuid": "no-such"}},
            ),
            headers=_auth(secretary_token),
        )
    data = await response.get_json()
    assert data["result"]["isError"] is True
    assert "не найдено" in data["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_arguments_list_rejected(client, secretary_token):
    """arguments: [] / "" / false → -32602, а не подмена на {} (круг 4)."""
    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        for bad in ([], "", False):
            response = await client.post(
                "/mcp",
                json=_rpc("tools/call", {"name": "d2_list_orgs", "arguments": bad}),
                headers=_auth(secretary_token),
            )
            data = await response.get_json()
            assert data["error"]["code"] == -32602, bad
            assert "arguments must be an object" in data["error"]["message"]


@pytest.mark.asyncio
async def test_mcp_empty_body_parse_error(client, secretary_token):
    """Пустое тело POST → -32700 parse error."""
    response = await client.post(
        "/mcp",
        data=b"",
        headers={**_auth(secretary_token), "Content-Type": "application/json"},
    )
    data = await response.get_json()
    assert data["error"]["code"] == -32700


@pytest.mark.asyncio
async def test_mcp_revoked_token_rejected(client, db_pool):
    async with db_pool() as session:
        raw = await create_token(session, SECRETARY["id"], "itolstov", "d2")
        await create_token(session, SECRETARY["id"], "itolstov", "d2")  # ревок первого

    signer, secretary, mcp_secretary, tables = _secretary_mocks()
    with contextlib.ExitStack() as stack:
        for m in (signer, secretary, mcp_secretary, *tables):
            stack.enter_context(m)
        response = await client.post(
            "/mcp", json=_rpc("initialize"), headers=_auth(raw)
        )
    assert response.status_code == 401
