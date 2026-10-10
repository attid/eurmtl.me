"""Дропдаун статусов списка: «Требует внимания» + «Черновики» + «Все»."""
import pytest
from unittest.mock import AsyncMock, patch
from contextlib import ExitStack
from tests.routers.test_d2_workspace import _secretaries_mock, _user_org_names_mock

SECRETARY_ID = 1837984392
PFM_ADDRESS = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"

def _tables_mock(**tables):
    from other.grist_tools import MTLGrist
    by_name = {}
    for attr, rows in tables.items():
        table = getattr(MTLGrist, attr, None)
        key = table.table_name if table is not None else attr
        by_name[key] = rows
    async def fake(table, *args, **kwargs):
        return list(by_name.get(table.table_name, []))
    return patch("other.grist_tools.grist_manager.load_table_data", new=AsyncMock(side_effect=fake))

def _seed():
    questions = [
        {"id": 1, "NUMBER": 118, "TITLE": "ActiveQ", "READING": 1, "ORG": "PFM"},
        {"id": 2, "NUMBER": 119, "TITLE": "DoneQ", "READING": 1, "ORG": "PFM"},
        {"id": 3, "NUMBER": 120, "TITLE": "DraftQ", "READING": 1, "ORG": "PFM"},
        {"id": 4, "NUMBER": 121, "TITLE": "ControlQ", "READING": 1, "ORG": "PFM"},
    ]
    data = [
        {"QUESTION_ID": 1, "READING": 1, "UUID": "u1", "TELEGRAM_LINK": "https://t.me/c/1863399780/1",
         "BODY": "<p>x</p>", "STATUS": "❗️ #active", "CREATED_BY": "@x", "ORG": "PFM"},
        {"QUESTION_ID": 2, "READING": 1, "UUID": "u2", "TELEGRAM_LINK": "https://t.me/c/1863399780/2",
         "BODY": "<p>y</p>", "STATUS": "✅ #done", "CREATED_BY": "@x", "ORG": "PFM"},
        {"QUESTION_ID": 3, "READING": 1, "UUID": "u3", "TELEGRAM_LINK": "",
         "BODY": "<p>draft</p>", "STATUS": "❗️ #active", "CREATED_BY": "@x", "ORG": "PFM"},
        {"QUESTION_ID": 4, "READING": 1, "UUID": "u4", "TELEGRAM_LINK": "https://t.me/c/1863399780/4",
         "BODY": "<p>z</p>", "STATUS": "‼️ #control", "CREATED_BY": "@x", "ORG": "PFM"},
    ]
    return questions, data

@pytest.mark.asyncio
async def test_attention_filter(client):
    """«Требует внимания»: active + control (draft тоже active — попадает)."""
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions, data = _seed()
    with ExitStack() as stack:
        for cm in (
            _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
            _user_org_names_mock({"PFM"}),
            _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        ):
            stack.enter_context(cm)
        resp = await client.get("/d2/fragment/edit?status=active&status_changed=1")
    body = (await resp.get_data()).decode()
    assert resp.status_code == 200
    assert "ActiveQ" in body and "ControlQ" in body and "DraftQ" in body
    assert "DoneQ" not in body

@pytest.mark.asyncio
async def test_drafts_filter(client):
    """«Черновики»: только вопросы без TELEGRAM_LINK."""
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions, data = _seed()
    with ExitStack() as stack:
        for cm in (
            _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
            _user_org_names_mock({"PFM"}),
            _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        ):
            stack.enter_context(cm)
        resp = await client.get("/d2/fragment/edit?status=drafts&status_changed=1")
    body = (await resp.get_data()).decode()
    assert resp.status_code == 200
    assert "DraftQ" in body
    assert "ActiveQ" not in body and "DoneQ" not in body and "ControlQ" not in body

@pytest.mark.asyncio
async def test_all_filter(client):
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions, data = _seed()
    with ExitStack() as stack:
        for cm in (
            _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
            _user_org_names_mock({"PFM"}),
            _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        ):
            stack.enter_context(cm)
        resp = await client.get("/d2/fragment/edit?status=all&status_changed=1")
    body = (await resp.get_data()).decode()
    assert resp.status_code == 200
    for t in ("ActiveQ", "DoneQ", "DraftQ", "ControlQ"):
        assert t in body

@pytest.mark.asyncio
async def test_default_view_is_attention_selected(client):
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions, data = _seed()
    with ExitStack() as stack:
        for cm in (
            _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
            _user_org_names_mock({"PFM"}),
            _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        ):
            stack.enter_context(cm)
        resp = await client.get("/d2/fragment/edit")
    body = (await resp.get_data()).decode()
    assert 'value="active" selected' in body
    assert "Требует внимания" in body
    # Дефолт — не только вид, но и ПРИМЕНЁННЫЙ фильтр: в таблице только
    # active/control (регрессия: вид «Требует внимания», данные — все).
    assert "ActiveQ" in body
    assert "ControlQ" in body
    assert "DraftQ" in body  # драфт со статусом active тоже виден
    assert "DoneQ" not in body


@pytest.mark.asyncio
async def test_search_without_status_finds_all(client):
    """Поиск без статуса ищет по всем (в т.ч. done): регрессия №695 —
    вопрос не теряется в «Требует внимания»."""
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions, data = _seed()
    with ExitStack() as stack:
        for cm in (
            _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
            _user_org_names_mock({"PFM"}),
            _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        ):
            stack.enter_context(cm)
        resp = await client.get("/d2/fragment/edit?q=119")
    body = (await resp.get_data()).decode()
    assert resp.status_code == 200
    assert "DoneQ" in body
    # Комбобокс на «Все» — статус не применялся.
    assert 'value="all" selected' in body


@pytest.mark.asyncio
async def test_search_plus_explicit_status_narrows(client):
    """Решение владельца 2026-10-11 (вариант 2): поиск ищет по всем, ЯВНЫЙ
    статус поверх поиска сужает найденное (119 done + status=active → пусто)."""
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions, data = _seed()
    with ExitStack() as stack:
        for cm in (
            _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
            _user_org_names_mock({"PFM"}),
            _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        ):
            stack.enter_context(cm)
        resp = await client.get("/d2/fragment/edit?q=11&status=active&status_changed=1")
    body = (await resp.get_data()).decode()
    assert resp.status_code == 200
    # q=11 матчит 118/119 (подстрока номера); active из них — 118.
    assert "ActiveQ" in body
    assert "DoneQ" not in body
    # Выбранный статус отображается как есть.
    assert 'value="active" selected' in body





@pytest.mark.asyncio
async def test_search_enter_ignores_rendered_status(client):
    """Enter в поиске сабмитит форму с отрисованным селектом (status=active
    с дефолтного экрана), но БЕЗ status_changed — сервер ищет по всем.
    Регрессия: q=1 (#next) с дефолтного экрана давал пусто."""
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions, data = _seed()
    with ExitStack() as stack:
        for cm in (
            _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
            _user_org_names_mock({"PFM"}),
            _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        ):
            stack.enter_context(cm)
        # Как браузер: q=1 + просочившийся status=active, флага нет.
        resp = await client.get("/d2/fragment/edit?q=1&status=active")
    body = (await resp.get_data()).decode()
    assert resp.status_code == 200
    # q=1 матчит 118/121 (подстрока номера «1»), не только active.
    assert "ActiveQ" in body
    assert "DoneQ" in body  # done-вопрос НЕ выфильтрован
