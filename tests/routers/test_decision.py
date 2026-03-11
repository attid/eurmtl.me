import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

from db.sql_models import Decisions
from routers.decision import get_full_text, migrate_decisions_to_grist


@pytest.mark.asyncio
async def test_decision_add_get(client):
    """Test GET /decision"""
    with patch("routers.decision.check_user_weight", new=AsyncMock(return_value=0)):
        response = await client.get("/decision")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_decision_add_post_no_auth(client):
    """Test POST /decision without authority"""
    with patch("routers.decision.check_user_weight", new=AsyncMock(return_value=0)):
        response = await client.post(
            "/decision",
            form={
                "question_number": "1",
                "short_subject": "Test",
                "inquiry": "Text",
                "status": "active",
                "reading": "1",
            },
        )
        # Should stay on page and show "need authority" flashed (not in response body usually if not using templates correctly in mock)
        # But here it just returns render_template
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_decision_get_number(client):
    """Test /decision/number"""
    with patch("routers.decision.gs_get_last_id", new=AsyncMock(return_value=[10])):
        response = await client.get("/decision/number")
        assert response.status_code == 200
        data = await response.get_json()
        assert data["number"] == "11"


@pytest.mark.asyncio
async def test_decision_update_text_unauthorized(client):
    """Test /decision/update_text with wrong token"""
    response = await client.post(
        "/decision/update_text",
        headers={"Authorization": "Bearer wrong_token"},
        json={"msg_url": "url", "msg_text": "text"},
    )
    assert response.status_code == 401


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
    questions = [
        {"id": 1, "NUMBER": 2, "TITLE": "Second"},
        {"id": 2, "NUMBER": 5, "TITLE": "Fifth"},
    ]
    question_data = [
        {"QUESTION_ID": 1, "READING": "1", "STATUS": "draft"},
        {"QUESTION_ID": 2, "READING": "3", "STATUS": "done"},
    ]

    with patch(
        "other.grist_tools.grist_manager.load_table_data",
        new=AsyncMock(side_effect=[questions, question_data]),
    ):
        response = await client.get("/d2/fragment/edit")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert body.index("5") < body.index("2")
    assert "done" in body


@pytest.mark.asyncio
async def test_decision_fragment_new_renders_sorted_templates(client):
    templates = [
        {"id": 2, "TITLE": "Zulu", "BODY": "z"},
        {"id": 1, "TITLE": "Alpha", "BODY": "a"},
    ]

    with patch(
        "other.grist_tools.grist_manager.load_table_data",
        new=AsyncMock(return_value=templates),
    ):
        response = await client.get("/d2/fragment/new")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert body.index("Alpha") < body.index("Zulu")


@pytest.mark.asyncio
async def test_show_decision_get_and_update_text_success(client, db_session, app):
    decision_uuid = "a" * 32
    decision = Decisions(
        uuid=decision_uuid,
        num=10,
        reading=1,
        description="Decision title",
        full_text="Old text",
        url="https://t.me/c/1/100",
        username="@alice",
        status="active",
        dt=datetime(2024, 1, 1, 12, 0, 0),
    )
    db_session.add(decision)
    await db_session.commit()

    response = await client.get(f"/d/{decision_uuid}")
    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Decision title" in body

    with patch(
        "routers.decision.config.eurmtl_key.get_secret_value",
        return_value="secret-token",
    ):
        response = await client.post(
            "/decision/update_text",
            headers={"Authorization": "Bearer secret-token"},
            json={"msg_url": decision.url, "msg_text": "Updated text"},
        )

    assert response.status_code == 200
    db_session.expire_all()
    updated = await db_session.get(Decisions, decision_uuid)
    assert updated.full_text == "Updated text"


@pytest.mark.asyncio
async def test_update_decision_text_handles_missing_and_not_found(client):
    with patch(
        "routers.decision.config.eurmtl_key.get_secret_value",
        return_value="secret-token",
    ):
        missing = await client.post(
            "/decision/update_text",
            headers={"Authorization": "Bearer secret-token"},
            json={"msg_url": "", "msg_text": ""},
        )
        not_found = await client.post(
            "/decision/update_text",
            headers={"Authorization": "Bearer secret-token"},
            json={"msg_url": "https://t.me/c/1/404", "msg_text": "Text"},
        )

    assert missing.status_code == 400
    assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_migrate_decisions_to_grist_creates_missing_rows(app, db_session):
    first = Decisions(
        uuid="a" * 32,
        num=10,
        reading=1,
        description="Question 10",
        full_text="Body 1",
        url="https://t.me/c/1/100",
        username="@alice",
        status="active",
        dt=datetime(2024, 1, 1, 12, 0, 0),
    )
    second = Decisions(
        uuid="b" * 32,
        num=10,
        reading=2,
        description="Question 10 second",
        full_text="Body 2",
        url="https://t.me/c/1/101",
        username="@alice",
        status="done",
        dt=datetime(2024, 1, 2, 12, 0, 0),
    )
    db_session.add(first)
    db_session.add(second)
    await db_session.commit()

    async with app.app_context():
        with (
            patch(
                "other.grist_tools.grist_manager.load_table_data",
                new=AsyncMock(
                    side_effect=[
                        [{"id": 99, "USERNAME": "alice"}],
                        [],
                        [],
                        [{"id": 501, "NUMBER": 10}],
                    ]
                ),
            ) as load_table_data,
            patch(
                "other.grist_tools.grist_manager.post_data",
                new=AsyncMock(),
            ) as post_data,
        ):
            await migrate_decisions_to_grist()

    assert load_table_data.await_count == 4
    assert post_data.await_count == 2
    questions_payload = post_data.await_args_list[0].args[1]
    question_data_payload = post_data.await_args_list[1].args[1]
    assert questions_payload["records"][0]["fields"]["NUMBER"] == 10
    assert len(question_data_payload["records"]) == 2
