import pytest
from unittest.mock import AsyncMock, patch

from routers.decision import get_full_text


@pytest.mark.asyncio
async def test_decision_redirects_to_d2_fragment_new(client):
    """Cutover: /decision и /d (создание) — редирект на d2-фрагмент-форму."""
    for url in ("/decision", "/d"):
        response = await client.get(url)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/d2/fragment/new")


@pytest.mark.asyncio
async def test_decision_post_also_redirects(client):
    """POST /d (старая форма) больше не поддерживается — редирект."""
    response = await client.post(
        "/d",
        form={
            "question_number": "1",
            "short_subject": "Test",
            "inquiry": "Text",
            "status": "active",
            "reading": "1",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/d2/fragment/new")


@pytest.mark.asyncio

def test_get_full_text_builds_links_and_footer():
    text = get_full_text(
        "❗️ #active",
        "<p>Hello</p><p><br></p>",
        [("https://r1",), None, ("https://r3",)],
        "uuid123",
        "@alice",
    )

    assert "Первое чтение" in text
    assert "Третье чтение" in text
    assert "Edit on eurmtl.me" in text
    assert "Added by @alice" in text


@pytest.mark.asyncio
async def test_decision_fragment_edit_renders_sorted_items(client):
    """Секретарь видит список; сортировка по номеру убыванию (5 раньше 2)."""
    async with client.session_transaction() as session:
        session["userdata"] = {"id": 1837984392, "username": "itolstov"}
        session["user_id"] = 1837984392
        session["d2_org"] = "PFM"

    questions = [
        {"id": 1, "NUMBER": 2, "TITLE": "Second", "ORG": "PFM"},
        {"id": 2, "NUMBER": 5, "TITLE": "Fifth", "ORG": "PFM"},
    ]
    question_data = [
        {"QUESTION_ID": 1, "READING": "1", "STATUS": "draft"},
        {"QUESTION_ID": 2, "READING": "3", "STATUS": "done"},
    ]

    async def fake(table, *a, **k):
        name = table.table_name
        if name == "D2_QUESTIONS":
            return questions
        if name == "D2_QUESTION_DATA":
            return question_data
        return []

    with (
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(side_effect=fake),
        ),
        patch(
            "other.grist_tools.user_org_names",
            new=AsyncMock(return_value={"PFM"}),
        ),
    ):
        response = await client.get("/d2/fragment/edit?status=all&status_changed=1")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert body.index("Fifth") < body.index("Second")
    assert "done" in body


@pytest.mark.asyncio
async def test_decision_fragment_new_renders_sorted_templates(client):
    templates = [
        {"id": 2, "TITLE": "Zulu", "BODY": "z", "ORG": "PFM"},
        {"id": 1, "TITLE": "Alpha", "BODY": "a", "ORG": "PFM"},
    ]

    async with client.session_transaction() as session:
        session["userdata"] = {"id": 1837984392, "username": "itolstov"}
        session["user_id"] = 1837984392
        session["d2_org"] = "PFM"

    with (
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(return_value=templates),
        ),
        patch(
            "other.grist_tools.user_org_names",
            new=AsyncMock(return_value={"PFM"}),
        ),
    ):
        response = await client.get("/d2/fragment/new")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert body.index("Alpha") < body.index("Zulu")
