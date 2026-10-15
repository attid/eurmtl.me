"""D2: покрытие роутов без тестов — /d2/copy, /d2/template/from, /d2/number,
отказные ветки /d2/<uuid>.

Регрессия инцидента 2026-10-15: cmd_d2_copy рендерил d2_form.html без
readings_total (500 с 224dd15, фикс 38e0864) — контракт «каждый рендер
d2_form передаёт readings_total и workspace context» закреплён тестом.
"""

import pytest
from unittest.mock import AsyncMock, patch

from tests.routers.test_d2_workspace import (
    GORA_ADDRESS,
    GORA_QUESTION_UUID,
    GORA_SIGNER_ID,
    PFM_ADDRESS,
    PFM_QUESTION_UUID,
    SECRETARY_ID,
    USDMM_QUESTION_UUID,
    _login,
    _secretaries_mock,
    _seed_questions,
    _set_org,
    _tables_mock,
    _user_org_names_mock,
)


def _pfm_visible_mocks():
    """Секретарь + подписант PFM: вопрос PFM виден, GORA/USDMM — нет."""
    return (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
    )


@pytest.mark.asyncio
async def test_copy_renders_form_with_readings_and_workspace(client):
    """Копия PFM-вопроса: 200, тема «(копия)», радио чтений = readings орги.

    Регрессия 224dd15: без readings_total рендер падал 500. Заодно
    закрепляет workspace context (org_names для d2_header_buttons.html).
    """
    await _login(client)
    await _set_org(client, "PFM")
    questions, question_data, templates = _seed_questions()
    vis_secr, vis_signer = _pfm_visible_mocks()
    with (
        vis_secr,
        vis_signer,
        _tables_mock(
            QUESTIONS=questions,
            QUESTION_DATA=question_data,
            QUESTION_TEMPLATES=templates,
        ),
    ):
        response = await client.get(f"/d2/copy?uuid={PFM_QUESTION_UUID}")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200, body[:500]
    assert "Принять отчёт казначея (копия)" in body
    assert "Копия вопроса №1" in body
    # PFM: readings=3 → три радио «Чтение», reading=1 предвыбран.
    assert body.count('name="reading"') == 3
    assert "checked" in body.split('name="reading"')[1][:120]
    # Следующий номер per-org: в сиде PFM — №1 → копия получает №2.
    assert 'value="2"' in body
    # Workspace-шапка отрендерилась (org_names не undefined).
    assert "Воркспейс: PFM" in body


@pytest.mark.asyncio
async def test_copy_unknown_uuid_404(client):
    await _login(client)
    await _set_org(client, "PFM")
    secr_m, sign_m = _pfm_visible_mocks()
    with secr_m, sign_m, _tables_mock():
        response = await client.get("/d2/copy?uuid=deadbeef")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_copy_invisible_org_404(client):
    """Чужая орга — как несуществующая: GORA-вопрос для PFM-юзера → 404."""
    await _login(client)  # itolstov: секретарь PFM, GORA не видит
    await _set_org(client, "PFM")
    questions, question_data, _ = _seed_questions()
    secr_m, sign_m = _pfm_visible_mocks()
    secr_m, sign_m = _pfm_visible_mocks()
    with (
        secr_m,
        sign_m,
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
    ):
        response = await client.get(f"/d2/copy?uuid={GORA_QUESTION_UUID}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_template_from_saves_question_body_and_title(client):
    """«Сохранить как шаблон»: post_data в QUESTION_TEMPLATES, редирект."""
    await _login(client)
    await _set_org(client, "PFM")
    questions, question_data, _ = _seed_questions()
    secr_m, sign_m = _pfm_visible_mocks()
    with (
        secr_m,
        sign_m,
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
    ):
        response = await client.post(
            "/d2/template/from",
            form={"uuid": PFM_QUESTION_UUID, "title": "Мой шаблон"},
        )

    assert response.status_code == 302
    assert f"/d2/{PFM_QUESTION_UUID}" in response.headers["Location"]
    post_mock.assert_awaited_once()
    fields = post_mock.await_args.args[1]["records"][0]["fields"]
    assert fields["TITLE"] == "Мой шаблон"
    assert fields["BODY"] == "Текст PFM-вопроса"


@pytest.mark.asyncio
async def test_template_from_empty_title_falls_back_to_question_title(client):
    await _login(client)
    await _set_org(client, "PFM")
    questions, question_data, _ = _seed_questions()
    secr_m, sign_m = _pfm_visible_mocks()
    with (
        secr_m,
        sign_m,
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
    ):
        await client.post(
            "/d2/template/from",
            form={"uuid": PFM_QUESTION_UUID, "title": "   "},
        )

    fields = post_mock.await_args.args[1]["records"][0]["fields"]
    assert fields["TITLE"] == "Принять отчёт казначея"


@pytest.mark.asyncio
async def test_template_from_unknown_uuid_404(client):
    await _login(client)
    await _set_org(client, "PFM")
    secr_m, sign_m = _pfm_visible_mocks()
    with (
        secr_m,
        sign_m,
        _tables_mock(),
        patch("other.grist_tools.grist_manager.post_data", new=AsyncMock()),
    ):
        response = await client.post(
            "/d2/template/from", form={"uuid": "deadbeef", "title": "x"}
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_number_without_workspace_returns_one(client):
    await _login(client)  # воркспейс в сессии не выбран
    secr_m, sign_m = _pfm_visible_mocks()
    with secr_m, sign_m, _tables_mock():
        response = await client.get("/d2/number")

    assert response.status_code == 200
    assert response.is_json
    assert (await response.get_json()) == {"number": "1"}


@pytest.mark.asyncio
async def test_number_counts_within_workspace_org_only(client):
    """Per-org нумерация: GORA №№1-2 в сидах → следующий 3, PFM не мешает."""
    await _login(client)
    await _set_org(client, "GORA")
    questions, _, _ = _seed_questions()
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _tables_mock(QUESTIONS=questions),
    ):
        response = await client.get("/d2/number")

    assert (await response.get_json()) == {"number": "3"}


@pytest.mark.asyncio
async def test_show_unknown_uuid_404(client):
    await _login(client)
    secr_m, sign_m = _pfm_visible_mocks()
    with (
        secr_m,
        sign_m,
        _tables_mock(),
    ):
        response = await client.get("/d2/deadbeef")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_show_invisible_org_404(client):
    """USDMM-вопрос для юзера без видимости USDMM → 404 (не палим факт)."""
    await _login(client, telegram_id=GORA_SIGNER_ID, username="nobody")
    questions, question_data, _ = _seed_questions()
    with (
        _secretaries_mock({}),
        _user_org_names_mock(set()),  # не подписант нигде, секретарств нет
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
    ):
        response = await client.get(f"/d2/{USDMM_QUESTION_UUID}")

    assert response.status_code == 404
