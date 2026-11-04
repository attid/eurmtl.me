"""D2: публичный embed-список вопросов орги по секретному токену.

Роут /d2/pub/<token> анонимный read-only: только № / тема / статус / ссылки
на TG-посты чтений. Тексты BODY и черновики (чтения без TELEGRAM_LINK)
не видны. Неверный токен = 404 без перечисления орг.
"""

import pytest
from unittest.mock import AsyncMock, patch

PFM_PUBLIC_TOKEN = "test_public_token_pfm"  # как в сиде стенда

QUESTIONS = [
    {"id": 1, "NUMBER": 3, "TITLE": "Вопрос с двумя чтениями", "ORG": "PFM"},
    {"id": 2, "NUMBER": 2, "TITLE": "Черновик без публикаций", "ORG": "PFM"},
    {"id": 3, "NUMBER": 1, "TITLE": "Вопрос с одним чтением", "ORG": "PFM"},
    {"id": 4, "NUMBER": 1, "TITLE": "TFM-вопрос (заглушка)", "ORG": "TFM"},
    {"id": 5, "NUMBER": 1, "TITLE": "USDMM-вопрос чужой орги", "ORG": "USDMM"},
]

QUESTION_DATA = [
    # Вопрос 3: чтение 2 идёт ПЕРЕД чтением 1 — на странице чтения по возрастанию.
    {
        "id": 11,
        "QUESTION_ID": 1,
        "READING": 2,
        "UUID": "aaaabbbbccccddddeeeeffff00002222",
        "TELEGRAM_LINK": "https://t.me/c/1863399780/101",
        "BODY": "СЕКРЕТНЫЙ ТЕКСТ второе чтение",
        "STATUS": "✅ #done",
        "CREATED_BY": "itolstov",
    },
    {
        "id": 12,
        "QUESTION_ID": 1,
        "READING": 1,
        "UUID": "aaaabbbbccccddddeeeeffff00001111",
        "TELEGRAM_LINK": "https://t.me/c/1863399780/100",
        "BODY": "СЕКРЕТНЫЙ ТЕКСТ первое чтение",
        "STATUS": "☑️ #next",
        "CREATED_BY": "itolstov",
    },
    # Вопрос 2: единственное чтение без TELEGRAM_LINK — черновик, невидим.
    {
        "id": 13,
        "QUESTION_ID": 2,
        "READING": 1,
        "UUID": "aaaabbbbccccddddeeeeffff00003333",
        "TELEGRAM_LINK": "",
        "BODY": "СЕКРЕТНЫЙ ТЕКСТ черновика",
        "STATUS": "❗️ #active",
        "CREATED_BY": "itolstov",
    },
    # Вопрос 3: одно опубликованное чтение.
    {
        "id": 14,
        "QUESTION_ID": 3,
        "READING": 1,
        "UUID": "aaaabbbbccccddddeeeeffff00005555",
        "TELEGRAM_LINK": "https://t.me/c/1863399780/102",
        "BODY": "СЕКРЕТНЫЙ ТЕКСТ одного чтения",
        "STATUS": "❗️ #active",
        "CREATED_BY": "itolstov",
    },
    # Вопрос 4 (TFM): чтение опубликовано, но орге нет строки в D2_PUBLIC.
    {
        "id": 15,
        "QUESTION_ID": 4,
        "READING": 1,
        "UUID": "aaaabbbbccccddddeeeeffff00009999",
        "TELEGRAM_LINK": "https://t.me/c/1863399780/199",
        "BODY": "СЕКРЕТНЫЙ ТЕКСТ TFM",
        "STATUS": "❗️ #active",
        "CREATED_BY": "itolstov",
    },
    # Вопрос 5 (USDMM): чужая орга — не рендерится по PFM-токену.
    {
        "id": 16,
        "QUESTION_ID": 5,
        "READING": 1,
        "UUID": "aaaabbbbccccddddeeeeffff00008888",
        "TELEGRAM_LINK": "https://t.me/c/1789207509/103",
        "BODY": "СЕКРЕТНЫЙ ТЕКСТ USDMM",
        "STATUS": "❗️ #active",
        "CREATED_BY": "itolstov",
    },
]

D2_PUBLIC_ROWS = [
    {"id": 1, "ORG": "PFM", "TOKEN": PFM_PUBLIC_TOKEN},
]


def _tables_mock(**tables):
    """Мок load_table_data по таблице (паттерн test_d2_publish._tables_mock)."""
    from other.grist_tools import MTLGrist

    by_name = {}
    for attr, rows in tables.items():
        table = getattr(MTLGrist, attr, None)
        key = table.table_name if table is not None else attr
        by_name[key] = rows

    async def fake(table, *args, **kwargs):
        value = by_name.get(table.table_name, [])
        return None if value is None else list(value)

    return patch(
        "other.grist_tools.grist_manager.load_table_data",
        new=AsyncMock(side_effect=fake),
    )


@pytest.fixture(autouse=True)
def _clear_public_cache():
    """Горячий кеш роута (TTL 5с) переживает тесты — чистим как остальные."""
    from routers.d2_public import public_tables_cache

    public_tables_cache.cache.clear()
    yield
    public_tables_cache.cache.clear()


def _pfm_tables():
    return _tables_mock(
        D2_PUBLIC=D2_PUBLIC_ROWS, QUESTIONS=QUESTIONS, QUESTION_DATA=QUESTION_DATA
    )


@pytest.mark.asyncio
async def test_public_embed_valid_token(client):
    """Валидный токен: список PFM, чтения asc, № desc, BODY не течёт."""
    with _pfm_tables():
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Вопрос с двумя чтениями" in body
    assert "Вопрос с одним чтением" in body
    assert 'href="https://t.me/c/1863399780/100"' in body
    assert 'href="https://t.me/c/1863399780/101"' in body
    # Чтения вопроса по возрастанию: Чтение 1 до Чтение 2.
    assert body.index("Чтение 1") < body.index("Чтение 2")
    # № по убыванию: вопрос №3 до №1 (черновик №2 скрыт).
    assert body.index("Вопрос с двумя чтениями") < body.index("Вопрос с одним чтением")
    # Тексты BODY не рендерятся нигде.
    assert "СЕКРЕТНЫЙ ТЕКСТ" not in body
    # Чужие орги не утекают.
    assert "TFM" not in body
    assert "USDMM" not in body


@pytest.mark.asyncio
async def test_public_embed_sort_number_desc(client):
    """№ по убыванию; статус — из последнего опубликованного чтения."""
    with _pfm_tables():
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    body = await response.get_data(as_text=True)
    assert body.index("Вопрос с двумя чтениями") < body.index("Вопрос с одним чтением")
    # Статус из max-чтения (✅ #done), статус чтения 1 (☑️ #next) не показан.
    assert "✅ #done" in body
    assert "☑️ #next" not in body


@pytest.mark.asyncio
async def test_public_embed_unknown_token_404(client):
    """Неверный токен — 404, одинаковый ответ без перечисления орг."""
    with _pfm_tables():
        response = await client.get("/d2/pub/deadbeef" + "0" * 24)
    assert response.status_code == 404

    with _pfm_tables():
        other = await client.get("/d2/pub/FFFFFF")
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_public_embed_draft_question_hidden(client):
    """Черновик (все чтения без TELEGRAM_LINK) не виден."""

    questions = [
        {"id": 1, "NUMBER": 1, "TITLE": "Опубликованный", "ORG": "PFM"},
        {"id": 2, "NUMBER": 2, "TITLE": "Черновик-с-номером", "ORG": "PFM"},
    ]
    question_data = [
        {
            "id": 11,
            "QUESTION_ID": 1,
            "READING": 1,
            "UUID": "aaaabbbbccccddddeeeeffff00001111",
            "TELEGRAM_LINK": "https://t.me/c/1863399780/100",
            "BODY": "текст",
            "STATUS": "❗️ #active",
        },
        {
            "id": 12,
            "QUESTION_ID": 2,
            "READING": 1,
            "UUID": "aaaabbbbccccddddeeeeffff00003333",
            "TELEGRAM_LINK": "",
            "BODY": "текст черновика",
            "STATUS": "❗️ #active",
        },
    ]
    with _tables_mock(
        D2_PUBLIC=D2_PUBLIC_ROWS, QUESTIONS=questions, QUESTION_DATA=question_data
    ):
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    body = await response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Опубликованный" in body
    assert "Черновик-с-номером" not in body


@pytest.mark.asyncio
async def test_public_embed_org_without_public_row_unreachable(client):
    """TFM и USDMM нет в D2_PUBLIC — их список недостижим ни под каким токеном."""
    with _pfm_tables():
        ok = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")
        tfm = await client.get("/d2/pub/tfm_dummy_token")
        empty_token = await client.get("/d2/pub/")

    assert ok.status_code == 200
    body = await ok.get_data(as_text=True)
    assert "TFM-вопрос" not in body
    assert "USDMM-вопрос чужой орги" not in body
    assert tfm.status_code == 404
    assert empty_token.status_code == 404


@pytest.mark.asyncio
async def test_public_embed_headers(client):
    """Заголовки embed-режима: noindex + разрешённый frame-ancestors."""
    with _pfm_tables():
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert response.headers["Content-Security-Policy"] == "frame-ancestors *"


@pytest.mark.asyncio
async def test_public_embed_empty_org_screen(client):
    """Токен валиден, но опубликованных вопросов нет — пустая заглушка."""
    questions = [{"id": 1, "NUMBER": 1, "TITLE": "Только черновик", "ORG": "PFM"}]
    question_data = [
        {
            "id": 11,
            "QUESTION_ID": 1,
            "READING": 1,
            "UUID": "aaaabbbbccccddddeeeeffff00001111",
            "TELEGRAM_LINK": "",
            "BODY": "текст",
            "STATUS": "❗️ #active",
        }
    ]
    with _tables_mock(
        D2_PUBLIC=D2_PUBLIC_ROWS, QUESTIONS=questions, QUESTION_DATA=question_data
    ):
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Только черновик" not in body
    assert "Опубликованных вопросов нет" in body


@pytest.mark.asyncio
async def test_public_embed_skips_bad_reading_and_missing_org(client):
    """Нечитаемый READING и вопрос без ORG не роняют роут."""
    questions = [
        {"id": 1, "NUMBER": 1, "TITLE": "Нормальный", "ORG": "PFM"},
        {"id": 2, "NUMBER": 2, "TITLE": "Без орги", "ORG": None},
    ]
    question_data = [
        {
            "id": 11,
            "QUESTION_ID": 1,
            "READING": 1,
            "UUID": "aaaabbbbccccddddeeeeffff00001111",
            "TELEGRAM_LINK": "https://t.me/c/1863399780/100",
            "BODY": "текст",
            "STATUS": "❗️ #active",
        },
        {
            "id": 12,
            "QUESTION_ID": 2,
            "READING": 1,
            "UUID": "aaaabbbbccccddddeeeeffff00003333",
            "TELEGRAM_LINK": "https://t.me/c/1863399780/101",
            "BODY": "текст",
            "STATUS": "❗️ #active",
        },
        {
            "id": 13,
            "QUESTION_ID": 1,
            "READING": "не-число",
            "UUID": "aaaabbbbccccddddeeeeffff00004444",
            "TELEGRAM_LINK": "https://t.me/c/1863399780/102",
            "BODY": "текст",
            "STATUS": "✅ #done",
        },
    ]
    with _tables_mock(
        D2_PUBLIC=D2_PUBLIC_ROWS, QUESTIONS=questions, QUESTION_DATA=question_data
    ):
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Нормальный" in body
    assert "Без орги" not in body


@pytest.mark.asyncio
async def test_public_embed_dirty_number_no_500(client):
    """Пустой/строковый/None NUMBER не роняют сортировку (было: 500)."""
    questions = [
        {"id": 1, "NUMBER": 2, "TITLE": "Нормальный номер", "ORG": "PFM"},
        {"id": 2, "NUMBER": "", "TITLE": "Пустой номер", "ORG": "PFM"},
        {"id": 3, "NUMBER": "12", "TITLE": "Строковый номер", "ORG": "PFM"},
        {"id": 4, "NUMBER": None, "TITLE": "None-номер", "ORG": "PFM"},
    ]
    question_data = [
        {
            "id": 11,
            "QUESTION_ID": qid,
            "READING": 1,
            "TELEGRAM_LINK": f"https://t.me/c/1863399780/10{qid}",
            "STATUS": "❗️ #active",
        }
        for qid in (1, 2, 3, 4)
    ]
    with _tables_mock(
        D2_PUBLIC=D2_PUBLIC_ROWS, QUESTIONS=questions, QUESTION_DATA=question_data
    ):
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "Нормальный номер" in body
    assert "Пустой номер" in body
    # ячейка с отсутствующим номером рендерится прочерком, не «None»
    assert '<td class="num">None</td>' not in body
    assert '<td class="num">—</td>' in body


@pytest.mark.asyncio
async def test_public_embed_filters_non_telegram_links(client):
    """javascript:/битые ссылки отсекаются, вопрос без валидных ссылок скрыт."""
    questions = [{"id": 1, "NUMBER": 1, "TITLE": "С грязной ссылкой", "ORG": "PFM"}]
    question_data = [
        {
            "id": 11,
            "QUESTION_ID": 1,
            "READING": 1,
            "TELEGRAM_LINK": "javascript:alert(1)",
            "STATUS": "❗️ #active",
        }
    ]
    with _tables_mock(
        D2_PUBLIC=D2_PUBLIC_ROWS, QUESTIONS=questions, QUESTION_DATA=question_data
    ):
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    assert "javascript:" not in body
    assert "С грязной ссылкой" not in body  # валидных чтений нет — вопрос скрыт


@pytest.mark.asyncio
async def test_public_embed_missing_table_404(client):
    """D2_PUBLIC отсутствует на проде (load_table_data → None) — 404, не 500."""
    with _tables_mock(D2_PUBLIC=None, QUESTIONS=[], QUESTION_DATA=[]):
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_public_embed_token_with_spaces_matches(client):
    """Пробелы вокруг токена в Grist-ячейке не ломают доступ (strip)."""
    rows = [{"id": 1, "ORG": "PFM", "TOKEN": f" {PFM_PUBLIC_TOKEN} "}]
    with _tables_mock(D2_PUBLIC=rows, QUESTIONS=[], QUESTION_DATA=[]):
        response = await client.get(f"/d2/pub/{PFM_PUBLIC_TOKEN}")

    assert response.status_code == 200
