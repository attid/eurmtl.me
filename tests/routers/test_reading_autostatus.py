import pytest
from unittest.mock import AsyncMock, patch
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

@pytest.mark.asyncio
async def test_reading_change_closes_previous(client):
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions = [{"id": 1, "NUMBER": 118, "TITLE": "Q", "READING": 1, "ORG": "PFM"}]
    data = [{"id": 10, "QUESTION_ID": 1, "READING": 1, "UUID": "u1",
             "TELEGRAM_LINK": "https://t.me/c/1863399780/1", "BODY": "<p>v1</p>",
             "STATUS": "❗️ #active", "CREATED_BY": "@x", "ORG": "PFM"}]
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
        _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        patch("routers.decision._d2_send_rich", new=AsyncMock(return_value=77)),
        patch("other.grist_tools.grist_manager.patch_data", new=AsyncMock()) as patch_mock,
        patch("other.grist_tools.grist_manager.post_data", new=AsyncMock()) as post_mock,
    ):
        resp = await client.post("/d2/u1", form={
            "short_subject": "Q", "inquiry": "<p>v2</p>",
            "status": "❗️ #active", "reading": "2",
        })
        assert resp.status_code == 302
        assert patch_mock.await_count >= 1
        posted = post_mock.await_args_list[-1].args[1]["records"][0]["fields"]
        assert posted["READING"] == 2 and posted["STATUS"] == "❗️ #active"
        assert posted["TELEGRAM_LINK"].endswith("/77")

@pytest.mark.asyncio
async def test_reading_change_keeps_canceled(client):
    """🔇 #canceled остаётся отменённым при смене чтения."""
    async with client.session_transaction() as s:
        s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
        s["user_id"] = SECRETARY_ID
        s["d2_org"] = "PFM"
    questions = [{"id": 1, "NUMBER": 118, "TITLE": "Q", "READING": 1, "ORG": "PFM"}]
    data = [{"id": 10, "QUESTION_ID": 1, "READING": 1, "UUID": "u1",
             "TELEGRAM_LINK": "https://t.me/c/1863399780/1", "BODY": "<p>v1</p>",
             "STATUS": "🔇 #canceled", "CREATED_BY": "@x", "ORG": "PFM"}]
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
        _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        patch("routers.decision._d2_send_rich", new=AsyncMock(return_value=78)),
        patch("other.grist_tools.grist_manager.patch_data", new=AsyncMock()),
        patch("other.grist_tools.grist_manager.post_data", new=AsyncMock()),
    ):
        await client.post("/d2/u1", form={
            "short_subject": "Q", "inquiry": "<p>v2</p>",
            "status": "❗️ #active", "reading": "2",
        })
        assert data[0]["STATUS"] == "🔇 #canceled"
