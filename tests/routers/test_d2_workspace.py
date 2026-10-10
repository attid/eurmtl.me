"""D2: воркспейс-модель — выбор организации и скоупинг страниц.

Сид стенда (tests/fixtures/d2_stand_seed.json):
- itolstov (1837984392) — секретарь PFM/GORA/USDMM (счёта 1/3/4);
- attid (1863399780) — подписант счёта 2 (GB6E7...), секретарств нет.
"""

import pytest
from unittest.mock import AsyncMock, patch

PFM_ADDRESS = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
GORA_ADDRESS = "GCVTXUMIUAENJH2XY4AOVGTJKPSCOXW3746PUH7QFGPBDOPPHYLIGORA"
USDMM_ADDRESS = "GDHDC4GBNPMENZAOBB4NCQ25TGZPDRK6ZGWUGSI22TVFATOLRPSUUSDM"

SECRETARY_ID = 1837984392
GORA_SIGNER_ID = 424242  # подписант GORA, не секретарь нигде

PFM_QUESTION_UUID = "aaaabbbbccccddddeeeeffff00001111"
GORA_QUESTION_UUID = "aaaabbbbccccddddeeeeffff00003333"
USDMM_QUESTION_UUID = "aaaabbbbccccddddeeeeffff00004444"

GORA_SECRETARY_ID = 555000  # секретарь GORA, не подписант нигде


@pytest.fixture(autouse=True)
def _clear_org_caches():
    """Горячие кеши видимости между тестами (TTL 60с/300с переживают тест)."""
    from other.grist_tools import org_signers_cache
    from routers.decision import secretary_ids_cache

    org_signers_cache.cache.clear()
    secretary_ids_cache.cache.clear()
    yield
    org_signers_cache.cache.clear()
    secretary_ids_cache.cache.clear()


def _secretaries_mock(by_account):
    return patch(
        "routers.decision._secretaries_by_account",
        new=AsyncMock(return_value=by_account),
    )


def _user_org_names_mock(names: set):
    """Мок user_org_names (подписантства) на уровне other.grist_tools."""
    return patch(
        "other.grist_tools.user_org_names",
        new=AsyncMock(return_value=names),
    )


def _tables_mock(**tables):
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


def _seed_questions():
    questions = [
        {
            "id": 1,
            "NUMBER": 1,
            "TITLE": "Принять отчёт казначея",
            "READING": 1,
            "ORG": "PFM",
        },
        {
            "id": 2,
            "NUMBER": 2,
            "TITLE": "Купить сервер для ноды",
            "READING": 2,
            "ORG": "GORA",
        },
        {
            "id": 3,
            "NUMBER": 3,
            "TITLE": "Спорный вопрос без чтений",
            "READING": 1,
            "ORG": "USDMM",
        },
    ]
    question_data = [
        {
            "id": 11,
            "QUESTION_ID": 1,
            "READING": 1,
            "UUID": PFM_QUESTION_UUID,
            "TELEGRAM_LINK": "https://t.me/c/1863399780/100",
            "BODY": "Текст PFM-вопроса",
            "STATUS": "❗️ #active",
        },
        {
            "id": 12,
            "QUESTION_ID": 2,
            "READING": 1,
            "UUID": GORA_QUESTION_UUID,
            "TELEGRAM_LINK": "",
            "BODY": "Текст GORA-вопроса",
            "STATUS": "✅ #done",
        },
        {
            "id": 13,
            "QUESTION_ID": 3,
            "READING": 1,
            "UUID": USDMM_QUESTION_UUID,
            "TELEGRAM_LINK": "https://t.me/c/1789207509/103",
            "BODY": "Текст USDMM-вопроса",
            "STATUS": "❗️ #active",
        },
    ]
    templates = [
        {"id": 1, "TITLE": "Простой вопрос", "BODY": "<p>Простой</p>", "ORG": "PFM"},
        {"id": 2, "TITLE": "Отчёт", "BODY": "<p>Отчёт</p>", "ORG": "PFM"},
        {"id": 3, "TITLE": "Заявка на расход", "BODY": "<p>Расход</p>", "ORG": "GORA"},
    ]
    return questions, question_data, templates


async def _login(client, telegram_id=SECRETARY_ID, username="itolstov"):
    async with client.session_transaction() as session:
        session["userdata"] = {"id": telegram_id, "username": username}
        session["user_id"] = telegram_id


async def _set_org(client, org):
    async with client.session_transaction() as session:
        session["d2_org"] = org


@pytest.mark.asyncio
async def test_d2_index_redirects_when_session_org_valid(client):
    await _login(client)
    await _set_org(client, "GORA")
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
    ):
        response = await client.get("/d2")
    assert response.status_code == 302
    assert response.headers["location"] == "/d2/fragment/edit?status=active"


@pytest.mark.asyncio
async def test_d2_workspace_picker_for_multiple_orgs(client):
    """Секретарь (сид: подписант всех адресов) с 2+ оргами видит выбор."""
    await _login(client)
    with (
        _secretaries_mock(
            {
                PFM_ADDRESS: {SECRETARY_ID},
                GORA_ADDRESS: {SECRETARY_ID},
                USDMM_ADDRESS: {SECRETARY_ID},
            }
        ),
    ):
        response = await client.get("/d2")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    for org in ("PFM", "GORA", "USDMM"):
        assert org in body
    assert "Выберите рабочее пространство" in body
    assert 'action="/d2/workspace"' in body


@pytest.mark.asyncio
async def test_d2_workspace_post_saves_session(client):
    await _login(client)
    with _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}):
        response = await client.post("/d2/workspace", form={"org": "GORA"})

    assert response.status_code == 302
    assert response.headers["location"] == "/d2/fragment/edit?status=active"
    async with client.session_transaction() as session:
        assert session["d2_org"] == "GORA"


@pytest.mark.asyncio
async def test_d2_workspace_post_invalid_org_flashes(client):
    await _login(client)
    with _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}):
        response = await client.post("/d2/workspace", form={"org": "PFM"})

    assert response.status_code == 302
    assert response.headers["location"] == "/d2"
    async with client.session_transaction() as session:
        assert "d2_org" not in session
        flashes = dict(session.get("_flashes", []))
    assert any("недоступна" in str(m) for m in flashes.values())


@pytest.mark.asyncio
async def test_d2_workspace_empty_screen_for_user_without_orgs(client):
    await _login(client, telegram_id=GORA_SIGNER_ID, username="nobody")
    with (
        _secretaries_mock({}),
        _user_org_names_mock(set()),
    ):
        response = await client.get("/d2")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "У вас нет организаций" in body
    assert "/d2/workspace" not in body


@pytest.mark.asyncio
async def test_edit_list_scoped_to_session_org(client):
    """Список: только вопросы текущей воркспейса, без org-фильтра и колонки."""
    await _login(client)
    await _set_org(client, "GORA")
    questions, question_data, _ = _seed_questions()

    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
    ):
        response = await client.get("/d2/fragment/edit?status=all")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Купить сервер для ноды" in body  # GORA-вопрос
    assert "Принять отчёт казначея" not in body  # PFM скрыт
    assert "Спорный вопрос без чтений" not in body  # USDMM скрыт
    assert "Все организации" not in body  # комбик-фильтр по оргам убран
    assert "<th>Орг</th>" not in body  # колонка «Орг» убрана


@pytest.mark.asyncio
async def test_edit_list_redirects_without_workspace(client):
    await _login(client)
    with _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}):
        response = await client.get("/d2/fragment/edit?status=all")
    assert response.status_code == 302
    assert response.headers["location"] == "/d2"


@pytest.mark.asyncio
async def test_template_picker_scoped_to_session_org(client):
    """В GORA виден только «Заявка на расход», PFM-шаблоны спрятаны."""
    await _login(client)
    await _set_org(client, "GORA")
    questions, question_data, templates = _seed_questions()

    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _tables_mock(
            QUESTION_TEMPLATES=templates,
            QUESTIONS=questions,
            QUESTION_DATA=question_data,
        ),
    ):
        response = await client.get("/d2/fragment/new")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Заявка на расход" in body
    assert "Простой вопрос" not in body
    assert "Отчёт" not in body


@pytest.mark.asyncio
async def test_form_ignores_foreign_template(client):
    """template_id чужой орги → чистая форма (prefill только тема/тело дефолт)."""
    await _login(client)
    await _set_org(client, "GORA")
    pfm_template = {
        "id": 1,
        "TITLE": "Простой вопрос",
        "BODY": "<p>Простой</p>",
        "ORG": "PFM",
    }

    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _tables_mock(QUESTION_TEMPLATES=[pfm_template]),
    ):
        response = await client.get("/d2/fragment/form?template_id=1")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Простой вопрос" not in body  # шаблон чужой орги проигнорирован
    # Комбик «Организация» в форме убран (в шапке остался select
    # переключения воркспейса — это не комбик выбора орги вопроса).
    assert 'id="org"' not in body
    assert 'name="short_subject"' in body  # форма отрендерилась


@pytest.mark.asyncio
async def test_add_uses_session_org_not_form(client):
    """POST /d2/add без поля org; org в форме игнорируется — берётся сессия."""
    await _login(client)
    await _set_org(client, "GORA")
    # POST создаёт вопрос №10: 1-я загрузка QUESTIONS — номера нет,
    # 2-я (после post_data) — появился.
    questions = [{"id": 50, "NUMBER": 10, "TITLE": "GORA topic", "READING": 1}]
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        if table.table_name == "QUESTIONS":
            calls["questions"] += 1
            return questions if calls["questions"] >= 2 else []
        return []

    msg = AsyncMock()
    msg.message_id = 777
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
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
                "question_number": "10",
                "short_subject": "GORA topic",
                "inquiry": "<p>Body</p>",
                "status": "❗️ #active",
                "reading": "1",
                # Чужой org в форме — должен быть проигнорирован.
                "org": "PFM",
            },
        )

    assert response.status_code == 302
    assert post_mock.await_count == 2
    questions_payload = post_mock.await_args_list[0].args[1]
    assert questions_payload["records"][0]["fields"]["ORG"] == "GORA"
    data_payload = post_mock.await_args_list[-1].args[1]
    fields = data_payload["records"][0]["fields"]
    # GORA: один канал 84131737 на все чтения.
    assert fields["TELEGRAM_LINK"] == "https://t.me/c/84131737/777"


@pytest.mark.asyncio
async def test_add_without_session_redirects_to_workspace_picker(client):
    await _login(client)
    with _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}):
        response = await client.post(
            "/d2/add",
            form={
                "question_number": "10",
                "short_subject": "Topic",
                "inquiry": "<p>Body</p>",
                "status": "❗️ #active",
                "reading": "1",
            },
        )
    assert response.status_code == 302
    assert response.headers["location"] == "/d2"
    async with client.session_transaction() as session:
        flashes = dict(session.get("_flashes", []))
    assert any("воркспейс" in str(m).lower() for m in flashes.values())


@pytest.mark.asyncio
async def test_question_screen_anonymous_gets_not_exist(client):
    """Аноним на /d2/<uuid> — отказ, не 200 (просмотр закрыт)."""
    response = await client.get(f"/d2/{PFM_QUESTION_UUID}")
    assert response.status_code == 404
    body = await response.get_data(as_text=True)
    assert "Decision not exist" in body


@pytest.mark.asyncio
async def test_question_screen_foreign_org_hidden(client):
    """Подписант GORA не видит PFM-вопрос — существование не палится."""
    await _login(client, telegram_id=GORA_SIGNER_ID, username="gora")
    questions, question_data, templates = _seed_questions()
    with (
        _secretaries_mock({GORA_ADDRESS: {999}}),  # GORA-секретарь — кто-то другой
        _user_org_names_mock({"GORA"}),
        _tables_mock(
            QUESTIONS=questions,
            QUESTION_DATA=question_data,
            QUESTION_TEMPLATES=templates,
        ),
    ):
        response = await client.get(f"/d2/{PFM_QUESTION_UUID}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_gora_signer_sees_gora_and_can_edit(client):
    """Подписант GORA (не секретарь): GORA-вопрос открывается, edit_allowed."""
    await _login(client, telegram_id=GORA_SIGNER_ID, username="gora")
    questions, question_data, _ = _seed_questions()

    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),  # секретарь PFM — не он
        _user_org_names_mock({"GORA"}),
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
    ):
        response = await client.get(f"/d2/{GORA_QUESTION_UUID}")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Купить сервер для ноды" in body
    # Поля не задизейблены (edit_allowed=True → user_weight=1).
    assert 'name="short_subject" class="form-control" required' in body
    assert "disabled" not in body.split('name="short_subject"')[1][:200]


@pytest.mark.asyncio
async def test_gora_signer_does_not_see_pfm_questions_in_list(client):
    await _login(client, telegram_id=GORA_SIGNER_ID, username="gora")
    await _set_org(client, "GORA")
    questions, question_data, _ = _seed_questions()

    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
    ):
        response = await client.get("/d2/fragment/edit?status=all")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Купить сервер для ноды" in body
    assert "Принять отчёт казначея" not in body


@pytest.mark.asyncio
async def test_gora_signer_creates_question_published_to_gora_channel(client):
    """Подписант GORA создаёт вопрос: публикация уходит в канал GORA 84131737."""
    await _login(client, telegram_id=GORA_SIGNER_ID, username="gora")
    await _set_org(client, "GORA")
    calls = {"questions": 0}

    async def fake(table, *a, **k):
        if table.table_name == "QUESTIONS":
            calls["questions"] += 1
            return (
                []
                if calls["questions"] < 2
                else [{"id": 50, "NUMBER": 11, "TITLE": "GORA topic", "READING": 1}]
            )
        return []

    msg = AsyncMock()
    msg.message_id = 888
    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        patch(
            "other.grist_tools.grist_manager.load_table_data",
            new=AsyncMock(side_effect=fake),
        ),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
        patch(
            "routers.decision.skynet_bot.send_message", new=AsyncMock(return_value=msg)
        ) as send_mock,
    ):
        response = await client.post(
            "/d2/add",
            form={
                "question_number": "11",
                "short_subject": "GORA topic",
                "inquiry": "<p>Body</p>",
                "status": "❗️ #active",
                "reading": "2",  # GORA: все чтения в один канал
            },
        )

    assert response.status_code == 302
    send_mock.assert_awaited_once()
    assert send_mock.await_args.kwargs["chat_id"] == -10084131737
    fields = post_mock.await_args_list[-1].args[1]["records"][0]["fields"]
    assert fields["ORG"] == "GORA"
    assert fields["TELEGRAM_LINK"] == "https://t.me/c/84131737/888"


@pytest.mark.asyncio
async def test_gora_secretary_sees_gora_publishes_ok_and_pfm_hidden(client):
    """Секретарь GORA (только EURMTL_secretaries на адрес GORA):
    GORA виден и публикуется, PFM не виден."""
    await _login(client, telegram_id=GORA_SECRETARY_ID, username="gorasec")
    await _set_org(client, "GORA")
    questions, question_data, _ = _seed_questions()

    with (
        _secretaries_mock({GORA_ADDRESS: {GORA_SECRETARY_ID}}),
        _user_org_names_mock(set()),  # не подписант нигде
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
    ):
        # Список: GORA виден, PFM скрыт.
        response = await client.get("/d2/fragment/edit?status=all")
        body = await response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Купить сервер для ноды" in body
        assert "Принять отчёт казначея" not in body

        # Публикация GORA-черновика.
        msg = AsyncMock()
        msg.message_id = 999
        with (
            patch(
                "other.grist_tools.grist_manager.patch_data", new=AsyncMock()
            ) as patch_mock,
            patch(
                "routers.decision.skynet_bot.send_message",
                new=AsyncMock(return_value=msg),
            ) as send_mock,
        ):
            response = await client.post(f"/d2/{GORA_QUESTION_UUID}/publish")

        assert response.status_code == 302
        send_mock.assert_awaited_once()
        assert send_mock.await_args.kwargs["chat_id"] == -10084131737
        patched = patch_mock.await_args.args[1]
        assert patched["records"][0]["fields"]["TELEGRAM_LINK"] == (
            "https://t.me/c/84131737/999"
        )


@pytest.mark.asyncio
async def test_gora_secretary_cannot_see_pfm_question(client):
    await _login(client, telegram_id=GORA_SECRETARY_ID, username="gorasec")
    questions, question_data, _ = _seed_questions()

    with (
        _secretaries_mock({GORA_ADDRESS: {GORA_SECRETARY_ID}}),
        _user_org_names_mock(set()),
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
    ):
        response = await client.get(f"/d2/{PFM_QUESTION_UUID}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_publish_rejected_for_signer_without_secretary_role(client):
    """Публикация не-секретарём (даже подписантом) → flash «только секретари»."""
    await _login(client, telegram_id=GORA_SIGNER_ID, username="gora")
    questions, question_data, _ = _seed_questions()

    with (
        _secretaries_mock({PFM_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _tables_mock(QUESTIONS=questions, QUESTION_DATA=question_data),
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
    ):
        response = await client.post(f"/d2/{GORA_QUESTION_UUID}/publish")

    assert response.status_code == 302
    send_mock.assert_not_awaited()
    async with client.session_transaction() as session:
        flashes = dict(session.get("_flashes", []))
    assert any("только секретари" in str(m) for m in flashes.values())


@pytest.mark.asyncio
async def test_next_number_is_per_org(client):
    """Per-org нумерация: max(NUMBER)+1 внутри орги, чужие номера не мешают."""
    from other.orgs_config import DEFAULT_ORG_NAME
    from routers.decision import _org_next_number

    questions = [
        {"id": 1, "NUMBER": 4, "ORG": "PFM"},
        {"id": 2, "NUMBER": 7, "ORG": "PFM"},
        {"id": 3, "NUMBER": 1, "ORG": "GORA"},
    ]
    assert _org_next_number(questions, "PFM") == 8   # только PFM-вопросы
    assert _org_next_number(questions, "GORA") == 2  # только GORA-вопросы
    assert _org_next_number(questions, "USDMM") == 1  # пусто — начинаем с 1
    assert _org_next_number(questions, DEFAULT_ORG_NAME) == 8


@pytest.mark.asyncio
async def test_add_same_number_in_other_org_allowed(client):
    """Номер, занятый в чужой орге, в этой орге свободен (per-org нумерация)."""
    await _login(client)
    await _set_org(client, "GORA")
    questions = [
        {"id": 1, "NUMBER": 1, "ORG": "PFM", "TITLE": "PFM one", "READING": 1},
    ]
    question_data = [
        {"QUESTION_ID": 1, "READING": "1", "UUID": "pfm1", "TELEGRAM_LINK": "https://t.me/c/1863399780/1"},
    ]
    with (
        patch("routers.decision.check_user_weight", new=AsyncMock(return_value=1)),
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _tables_mock(
            QUESTIONS=questions,
            QUESTION_DATA=question_data,
        ),
        patch(
            "other.grist_tools.grist_manager.post_data", new=AsyncMock()
        ) as post_mock,
        patch("routers.decision.skynet_bot.send_message", new=AsyncMock()) as send_mock,
    ):
        response = await client.post(
            "/d2/add",
            form={
                "question_number": "1",
                "short_subject": "GORA two",
                "inquiry": "<p>x</p>",
                "status": "❗️ #active",
                "reading": "1",
            },
        )
    # 302 на новый вопрос, а не flash «уже существует».
    assert response.status_code == 302
    flashes = {}
    async with client.session_transaction() as session:
        flashes = dict(session.get("_flashes", []))
    assert not any("уже существует" in str(m) for m in flashes.values())
    assert send_mock.await_count == 1
