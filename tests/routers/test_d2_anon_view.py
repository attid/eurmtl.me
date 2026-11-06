"""Публичный read-only просмотр вопроса по ссылке (решение владельца
2026-11-05, вариант B): аноним с неугадываемым uuid из поста канала
читает вопрос без кнопок правки; несуществующие uuid — 404 как раньше;
залогиненный чужак — 404 (гейт видимости орги не ослаблен)."""

import contextlib

import pytest
from unittest.mock import AsyncMock, patch

from tests.routers.test_d2_workspace import (
    PFM_ADDRESS,
    _secretaries_mock,
    _tables_mock,
    _user_org_names_mock,
)

SECRETARY_ID = 1837984392
SECRETARY_SESSION = {"id": SECRETARY_ID, "username": "itolstov"}
PUBLISHED_UUID = "5e458fb9f82d4445b5954298d39a3831"
DRAFT_UUID = "d" + "0" * 31
DRAFT3_UUID = "c" + "0" * 31

QUESTIONS = [
    {"id": 1, "NUMBER": 704, "TITLE": "Об инвестиции", "READING": 3, "ORG": "PFM"},
    {"id": 2, "NUMBER": 705, "TITLE": "Черновик-вопрос", "READING": 1, "ORG": "PFM"},
    {"id": 3, "NUMBER": 1, "TITLE": "Чужая орга", "READING": 1, "ORG": "GORA"},
    {"id": 4, "NUMBER": 1, "TITLE": "Заглушка TFM", "READING": 1, "ORG": "TFM"},
]
DATA = [
    {
        "id": 15,
        "QUESTION_ID": 1,
        "READING": 1,
        "UUID": "e" + "0" * 31,
        "TELEGRAM_LINK": "https://t.me/c/1863399780/11",
        "BODY": "<p>Первое чтение</p>",
        "STATUS": "☑️ #next",
        "CREATED_BY": "@x",
    },
    {
        "id": 10,
        "QUESTION_ID": 1,
        "READING": 2,
        "UUID": PUBLISHED_UUID,
        "TELEGRAM_LINK": "https://t.me/c/1652080456/42",
        "BODY": "<p>Тело опубликованного чтения</p>",
        "STATUS": "❗️ #active",
        "CREATED_BY": "@x",
    },
    {
        # Черновик 3-го чтения того же вопроса: анониму в навигации не
        # светится (решение 2026-11-05).
        "id": 13,
        "QUESTION_ID": 1,
        "READING": 3,
        "UUID": DRAFT3_UUID,
        "TELEGRAM_LINK": "",
        "BODY": "<p>Черновик третьего</p>",
        "STATUS": "❗️ #active",
        "CREATED_BY": "@x",
    },
    {
        "id": 11,
        "QUESTION_ID": 2,
        "READING": 1,
        "UUID": DRAFT_UUID,
        "TELEGRAM_LINK": "",
        "BODY": "<p>Тело черновика</p>",
        "STATUS": "❗️ #active",
        "CREATED_BY": "@x",
    },
    {
        "id": 12,
        "QUESTION_ID": 3,
        "READING": 1,
        "UUID": "a" * 32,
        "TELEGRAM_LINK": "https://t.me/c/1767165598/7",
        "BODY": "<p>GORA body</p>",
        "STATUS": "❗️ #active",
        "CREATED_BY": "@x",
    },
    {
        # Орга-заглушка TFM (пустой main_address): по ссылке читается
        # анонимом (решение 2026-11-05, п. 4).
        "id": 14,
        "QUESTION_ID": 4,
        "READING": 1,
        "UUID": "b" * 32,
        "TELEGRAM_LINK": "",
        "BODY": "<p>TFM body</p>",
        "STATUS": "❗️ #active",
        "CREATED_BY": "@x",
    },
]


@pytest.fixture(autouse=True)
def _clear_question_tables_cache():
    """Кеш D2_* таблиц (TTL 5с) переживает тесты — чистим (как в
    test_d2_workspace)."""
    from routers.decision import question_tables_cache

    question_tables_cache.cache.clear()
    yield
    question_tables_cache.cache.clear()


@contextlib.contextmanager
def _mocks():
    """Комбинированный контекст: секретарство, орги и таблицы D2."""
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM", "GORA"}),
        _tables_mock(D2_QUESTIONS=QUESTIONS, D2_QUESTION_DATA=DATA),
    ):
        yield


@pytest.mark.asyncio
async def test_anon_reads_published_question(client):
    """Аноним по ссылке читает вопрос: тело/статус/кнопки TG на месте,
    воркспейс-элементы и кнопки правки — нет."""
    with _mocks():
        resp = await client.get(f"/d2/{PUBLISHED_UUID}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "Тело опубликованного чтения" in body
    assert "Об инвестиции" in body
    assert "Открыть в Telegram" in body
    # Бейдж org — реальная орга вопроса, не сессионная/None (ревью аги P1).
    assert ">PFM<" in body
    assert ">None<" not in body
    # Поля read-only: дизейбл на инпутах (ревью аги: проверка атрибутов).
    assert 'id="short_subject"' in body and "disabled" in body
    # Воркспейс-элементы и правка скрыты.
    assert "Копировать в новый вопрос" not in body
    assert "Сохранить как шаблон" not in body
    assert "Создать транзакцию" not in body
    assert "К списку вопросов" not in body
    assert "Создать вопрос" not in body
    assert "Сохранить и обновить" not in body
    assert 'action="/d2/template/from"' not in body


@pytest.mark.asyncio
async def test_anon_reads_via_canonical_d_link(client):
    """Каноническая ссылка из постов /d/<uuid>: аноним после редиректа
    читает вопрос (ревью аги: тестировался только прямой /d2/...)."""
    with _mocks():
        resp = await client.get(f"/d/{PUBLISHED_UUID}", follow_redirects=True)
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "Тело опубликованного чтения" in body


@pytest.mark.asyncio
async def test_anon_reads_foreign_org_question(client):
    """Аноним читает вопрос чужой/любой оргы (решение 4: гейт видимости
    орги для анонима не применяется; ревью аги — кейс GORA)."""
    with _mocks():
        resp = await client.get(f"/d2/{'a' * 32}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "GORA body" in body
    assert ">GORA<" in body


@pytest.mark.asyncio
async def test_anon_unknown_uuid_still_404(client):
    """Несуществующие uuid не палим — тот же 404, что и раньше."""
    with _mocks():
        resp = await client.get(f"/d2/{'f' * 32}")
    assert resp.status_code == 404
    assert "Decision not exist" in await resp.get_data(as_text=True)


@pytest.mark.asyncio
async def test_anon_reads_draft_with_badge(client):
    """Аноним с ссылкой на черновик — read-only с бейджем «черновик»,
    без кнопки публикации (ревью аги, круг 18: strict DOM-гейт)."""
    with _mocks():
        resp = await client.get(f"/d2/{DRAFT_UUID}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "Тело черновика" in body
    assert "черновик" in body
    assert "Опубликовать" not in body
    assert "/publish" not in body


@pytest.mark.asyncio
async def test_anon_post_does_not_mutate(client):
    """POST анонима — 404 «как несуществующий», мутаций нет:
    POST не должен отвечать 200."""
    with (
        _mocks(),
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
    ):
        resp = await client.post(
            f"/d2/{PUBLISHED_UUID}",
            form={
                "short_subject": "hack",
                "inquiry": "<p>hack</p>",
                "status": "✅ #done",
                "reading": "2",
            },
        )
        assert resp.status_code == 404
    patch_mock.assert_not_awaited()
    post_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_anon_nav_hides_foreign_drafts(client):
    """Чужие черновики не светятся в навигации чтений анонима (nav
    рендерится при двух опубликованных чтениях, черновик r3 в нём
    отсутствует)."""
    with _mocks():
        resp = await client.get(f"/d2/{PUBLISHED_UUID}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    # Навигация отрендерилась (два опубликованных чтения).
    assert f"/d2/{'e' + '0' * 31}" in body
    assert f"/d2/{PUBLISHED_UUID}" in body
    # Черновик r3 — нет.
    assert DRAFT3_UUID not in body
    assert "Черновик третьего" not in body
    # По прямой ссылке на черновик аноним его видит: nav — все три,
    # черновик с бейджем (решение: текущее чтение остаётся в nav).
    resp = await client.get(f"/d2/{DRAFT3_UUID}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "Черновик третьего" in body
    assert DRAFT3_UUID in body
    assert PUBLISHED_UUID in body
    assert "черновик" in body


@pytest.mark.asyncio
async def test_anon_reads_tfm_placeholder_org(client):
    """Орга-заглушка с пустым main_address (TFM) читается анонимом
    (решение 2026-11-05, п. 4)."""
    with _mocks():
        resp = await client.get(f"/d2/{'b' * 32}")
    assert resp.status_code == 200
    assert "TFM body" in await resp.get_data(as_text=True)


@pytest.mark.parametrize(
    "broken_userdata", [{}, {"id": None}, {"id": "bad_id"}, "broken_string"]
)
@pytest.mark.asyncio
async def test_broken_userdata_treated_as_anon(client, broken_userdata):
    """Полуавторизованная сессия (пустой/битый userdata) = аноним:
    GET 200 read-only, POST 404 (аноним = нет валидного telegram id)."""
    with (
        _mocks(),
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
    ):
        async with client.session_transaction() as s:
            s["userdata"] = broken_userdata
        resp = await client.get(f"/d2/{PUBLISHED_UUID}")
        assert resp.status_code == 200
        assert "Тело опубликованного чтения" in await resp.get_data(as_text=True)
        resp_post = await client.post(
            f"/d2/{PUBLISHED_UUID}",
            form={
                "short_subject": "x",
                "inquiry": "<p>x</p>",
                "status": "✅ #done",
                "reading": "2",
            },
        )
        assert resp_post.status_code == 404
    patch_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_without_channel_flashes(client):
    """channel=None (канал не настроен): flash с объяснением вместо
    молчаливого редиректа."""
    q_uuid = "3" * 32
    questions = [
        {"id": 30, "NUMBER": 1, "TITLE": "Q", "READING": 1, "ORG": "PFM"},
    ]
    data = [
        {
            "id": 300,
            "QUESTION_ID": 30,
            "READING": 1,
            "UUID": q_uuid,
            "TELEGRAM_LINK": "",
            "BODY": "<p>b</p>",
            "STATUS": "❗️ #active",
            "CREATED_BY": "@x",
        }
    ]
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
        _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
        patch("routers.decision.resolve_channel", new=AsyncMock(return_value=None)),
    ):
        async with client.session_transaction() as s:
            s["userdata"] = SECRETARY_SESSION
            s["user_id"] = SECRETARY_SESSION["id"]
        # PFM-чтение с замоканным resolve_channel → None: ветка
        # «канал не настроен».
        resp = await client.post(f"/d2/{q_uuid}/publish")
        assert resp.status_code == 302
        async with client.session_transaction() as s:
            flashes = dict(s.get("_flashes", []))
    assert any("не настроен" in str(m) for m in flashes.values())


@pytest.mark.asyncio
async def test_anon_return_to_saved_for_login_redirect(client):
    """return_to сохраняется анониму — после логина вернёт на вопрос."""
    with _mocks():
        await client.get(f"/d2/{PUBLISHED_UUID}")
        async with client.session_transaction() as s:
            assert s.get("return_to", "").endswith(f"/d2/{PUBLISHED_UUID}")


@pytest.mark.asyncio
async def test_anon_short_canonical_uuid_404(client):
    """Битая каноническая ссылка /d/<короткий> — 404."""
    resp = await client.get("/d/shortuuid")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_logged_in_foreign_org_still_404(client):
    """Залогиненный без прав на оргу — прежний 404 (гейт не ослаблен):
    и GET, и POST, Grist не мутируется."""
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
        _tables_mock(D2_QUESTIONS=QUESTIONS, D2_QUESTION_DATA=DATA),
        patch(
            "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
        ) as patch_mock,
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
    ):
        async with client.session_transaction() as s:
            s["userdata"] = {"id": SECRETARY_ID, "username": "itolstov"}
            s["user_id"] = SECRETARY_ID
        resp = await client.get(f"/d2/{'a' * 32}")
        assert resp.status_code == 404
        resp_post = await client.post(
            f"/d2/{'a' * 32}",
            form={
                "short_subject": "x",
                "inquiry": "<p>x</p>",
                "status": "✅ #done",
                "reading": "1",
            },
        )
        assert resp_post.status_code == 404
        # Публикация чужой орги — тоже 404 (свой гейт в cmd_d2_publish;
        # ревью аги, круг 24, P2-3).
        resp_publish = await client.post(f"/d2/{'a' * 32}/publish")
        assert resp_publish.status_code == 404
    patch_mock.assert_not_awaited()
    post_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_anon_blocked_on_mutation_endpoints(client):
    """Смежные эндпоинты для анонима закрыты прежними гейтами
    (_org_visible → 404): publish/copy/template_from; upload_image —
    403 по воркспейс-гейту (редактор воркспейса не выбран)."""
    with _mocks():
        publish = await client.post(f"/d2/{PUBLISHED_UUID}/publish")
        copy = await client.get(f"/d2/copy?uuid={PUBLISHED_UUID}")
        template = await client.post(
            "/d2/template/from",
            form={"uuid": PUBLISHED_UUID, "title": "t"},
        )
        upload = await client.post("/d2/upload_image")
    assert publish.status_code == 404
    assert copy.status_code == 404
    assert template.status_code == 404
    assert upload.status_code == 403


@pytest.mark.asyncio
async def test_member_question_badge_vs_workspace_header(client):
    """Бейдж вопроса — орга ВОПРОСА, шапка — сессионный воркспейс: член
    с воркспейсом PFM открывает доступный вопрос GORA
    (рассинхрон UI/сессии)."""
    with _mocks():
        async with client.session_transaction() as s:
            s["userdata"] = SECRETARY_SESSION
            s["user_id"] = SECRETARY_SESSION["id"]
            s["d2_org"] = "PFM"
        resp = await client.get(f"/d2/{'a' * 32}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert ">GORA<" in body  # бейдж вопроса
    assert "Воркспейс: PFM" in body  # шапка — сессия не уехала


@pytest.mark.asyncio
async def test_member_sees_edit_elements(client):
    """Секретарь видит воркспейс-элементы (регрессия: ничего не спрятали
    лишнего у своих)."""
    with _mocks():
        async with client.session_transaction() as s:
            s["userdata"] = SECRETARY_SESSION
            s["user_id"] = SECRETARY_SESSION["id"]
            s["d2_org"] = "PFM"
        resp = await client.get(f"/d2/{PUBLISHED_UUID}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "К списку вопросов" in body
    assert "Копировать в новый вопрос" in body
    # Форма доступна: поле темы не disabled, кнопка сохранения и
    # радио-чтения на месте.
    assert 'value="Об инвестиции" >' in body  # без disabled после value
    assert "Сохранить и обновить в Telegram" in body
    assert 'name="reading"' in body


@pytest.mark.asyncio
async def test_typo_telegram_link_treated_as_draft(client):
    """Битая ссылка в ячейке (без схемы) = черновик, а не «зависшее»
    состояние: бейдж + кнопка «Опубликовать» у секретаря, кнопки TG
    нет ( — единый предикат публикации)."""
    typo_uuid = "9" * 32
    questions = [
        {"id": 9, "NUMBER": 900, "TITLE": "Опечатка", "READING": 1, "ORG": "PFM"},
    ]
    data = [
        {
            "id": 90,
            "QUESTION_ID": 9,
            "READING": 1,
            "UUID": typo_uuid,
            "TELEGRAM_LINK": "t.me/без-схемы",
            "BODY": "<p>body</p>",
            "STATUS": "❗️ #active",
            "CREATED_BY": "@x",
        }
    ]
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
        _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
    ):
        async with client.session_transaction() as s:
            s["userdata"] = SECRETARY_SESSION
            s["user_id"] = SECRETARY_SESSION["id"]
            s["d2_org"] = "PFM"
        resp = await client.get(f"/d2/{typo_uuid}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "черновик" in body
    assert "Опубликовать" in body
    assert "Открыть в Telegram" not in body


@pytest.mark.asyncio
async def test_telegram_link_with_query_params_still_published(client):
    """Ссылка с query/якорем (?single, #f) — валидный пост, не «черновик»:
    нормализация в _row_telegram_link."""
    q_uuid = "7" * 32
    questions = [
        {"id": 7, "NUMBER": 700, "TITLE": "Q", "READING": 1, "ORG": "PFM"},
    ]
    data = [
        {
            "id": 70,
            "QUESTION_ID": 7,
            "READING": 1,
            "UUID": q_uuid,
            "TELEGRAM_LINK": "https://t.me/c/1652080456/99?single#f",
            "BODY": "<p>body</p>",
            "STATUS": "❗️ #active",
            "CREATED_BY": "@x",
        }
    ]
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
        _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
    ):
        async with client.session_transaction() as s:
            s["userdata"] = SECRETARY_SESSION
            s["user_id"] = SECRETARY_SESSION["id"]
            s["d2_org"] = "PFM"
        resp = await client.get(f"/d2/{q_uuid}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    # Бейдж черновика (is_draft) не рендерится: слово «черновик» есть и в
    # лейблах формы секретаря — проверяем именно бейдж.
    assert "badge bg-warning-lt ms-1" not in body
    assert "Открыть в Telegram" in body
    # Кнопка ведёт на нормализованный URL без query/якоря.
    assert "https://t.me/c/1652080456/99" in body
    assert "?single" not in body


@pytest.mark.asyncio
async def test_channel_link_without_message_id_is_draft(client):
    """Ссылка на сам приватный канал (без id сообщения) — не «опубликован»:
    бейдж черновика и «Опубликовать» у секретаря."""
    q_uuid = "8" * 32
    questions = [
        {"id": 8, "NUMBER": 800, "TITLE": "Q", "READING": 1, "ORG": "PFM"},
    ]
    data = [
        {
            "id": 80,
            "QUESTION_ID": 8,
            "READING": 1,
            "UUID": q_uuid,
            "TELEGRAM_LINK": "https://t.me/c/1652080456",
            "BODY": "<p>body</p>",
            "STATUS": "❗️ #active",
            "CREATED_BY": "@x",
        }
    ]
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"PFM"}),
        _tables_mock(D2_QUESTIONS=questions, D2_QUESTION_DATA=data),
    ):
        async with client.session_transaction() as s:
            s["userdata"] = SECRETARY_SESSION
            s["user_id"] = SECRETARY_SESSION["id"]
            s["d2_org"] = "PFM"
        resp = await client.get(f"/d2/{q_uuid}")
    assert resp.status_code == 200
    body = await resp.get_data(as_text=True)
    assert "badge bg-warning-lt ms-1" in body  # бейдж черновика
    assert "Опубликовать" in body
    assert "Открыть в Telegram" not in body
