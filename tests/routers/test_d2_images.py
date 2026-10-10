"""D2: картинки вопросов — upload в Grist Attachments и публичная отдача.

Покрывает:
- POST /d2/upload_image: гейт воркспейса+редактора, размер, тип;
- GET /d2/img/<row_id>: публичная отдача, content-type по магическим байтам,
  404, кеш-заголовки.

Grist attachment-методы (post_attachment/get_attachment) мокаются на уровне
grist_manager; таблица D2_IMAGES читается как обычная через load_table_data.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from werkzeug.datastructures import FileStorage

from tests.routers.test_d2_workspace import (
    GORA_ADDRESS,
    GORA_SIGNER_ID,
    SECRETARY_ID,
    _secretaries_mock,
    _user_org_names_mock,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_BYTES = PNG_MAGIC + b"fake png body"


def _png_file(name="test.png", content=PNG_BYTES):
    return FileStorage(
        stream=io.BytesIO(content), filename=name, content_type="image/png"
    )


async def _login_gora_editor(client, telegram_id=SECRETARY_ID, username="itolstov"):
    async with client.session_transaction() as session:
        session["userdata"] = {"id": telegram_id, "username": username}
        session["user_id"] = telegram_id
        session["d2_org"] = "GORA"


def _post_attachment_mock(row_id=101):
    return patch(
        "other.grist_tools.grist_manager.post_attachment",
        new=AsyncMock(return_value=row_id),
    )


def _d2_images_rows(rows):
    """Мок load_table_data: D2_IMAGES отдаёт rows, остальные таблицы пусты."""

    async def fake(table, *args, **kwargs):
        return list(rows) if table.table_name == "D2_IMAGES" else []

    return patch(
        "other.grist_tools.grist_manager.load_table_data",
        new=AsyncMock(side_effect=fake),
    )


@pytest.fixture(autouse=True)
def _clear_caches():
    from other.grist_tools import org_signers_cache
    from routers.decision import secretary_ids_cache

    org_signers_cache.cache.clear()
    secretary_ids_cache.cache.clear()
    yield
    org_signers_cache.cache.clear()
    secretary_ids_cache.cache.clear()


@pytest.mark.asyncio
async def test_upload_editor_gets_url(client):
    """Редактор GORA грузит png → 200 {url: /d2/img/<row_id>}."""
    await _login_gora_editor(client)
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=101) as upload_mock,
    ):
        response = await client.post("/d2/upload_image", files={"file": _png_file()})

    assert response.status_code == 200
    assert await response.get_json() == {"url": "/d2/img/101"}
    upload_mock.assert_awaited_once()
    table, file_bytes, filename, fields = upload_mock.await_args.args
    assert table.table_name == "D2_IMAGES"
    assert file_bytes == PNG_BYTES
    assert filename == "test.png"
    assert fields["ORG"] == "GORA"
    assert fields["UPLOADED_BY"] == "@itolstov"
    assert fields["CREATED_AT"]


@pytest.mark.asyncio
async def test_upload_gora_signer_is_editor_too(client):
    """Подписант GORA (не секретарь) — тоже редактор, грузить может."""
    await _login_gora_editor(client, telegram_id=GORA_SIGNER_ID, username="gora")
    with (
        _secretaries_mock({GORA_ADDRESS: {999}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=7),
    ):
        response = await client.post("/d2/upload_image", files={"file": _png_file()})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_upload_not_editor_forbidden(client):
    """Не-редактор (не секретарь и не подписант) → 403 JSON."""
    await _login_gora_editor(client, telegram_id=GORA_SIGNER_ID, username="outsider")
    with (
        _secretaries_mock({GORA_ADDRESS: {999}}),
        _user_org_names_mock(set()),
        _post_attachment_mock(row_id=7) as upload_mock,
    ):
        response = await client.post("/d2/upload_image", files={"file": _png_file()})
    assert response.status_code == 403
    assert (await response.get_json())["error"] == "forbidden"
    upload_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_without_workspace_forbidden(client):
    """Без воркспейса в сессии — отказ, даже если пользователь редактор."""
    await _login_gora_editor(client)
    async with client.session_transaction() as session:
        session.pop("d2_org")
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=7),
    ):
        response = await client.post("/d2/upload_image", files={"file": _png_file()})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_anonymous_redirects(client):
    """Аноним без сессии → отказ (не 200)."""
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=7),
    ):
        response = await client.post("/d2/upload_image", files={"file": _png_file()})
    assert response.status_code in (302, 403)


@pytest.mark.asyncio
async def test_upload_too_large_rejected(client):
    """> 5 МБ → 413, Grist не вызывается."""
    await _login_gora_editor(client)
    big = PNG_MAGIC + b"x" * (5 * 1024 * 1024)
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=7) as upload_mock,
    ):
        response = await client.post(
            "/d2/upload_image", files={"file": _png_file(content=big)}
        )
    assert response.status_code == 413
    upload_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_not_image_rejected(client):
    """Контент не картинка (по магическим байтам) → 400."""
    await _login_gora_editor(client)
    fake = FileStorage(
        stream=io.BytesIO(b"just text, not an image"),
        filename="fake.png",
        content_type="image/png",
    )
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=7) as upload_mock,
    ):
        response = await client.post("/d2/upload_image", files={"file": fake})
    assert response.status_code == 400
    upload_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_unsupported_content_type_rejected(client):
    """Content-type вне whitelist (pdf) → 400."""
    await _login_gora_editor(client)
    fake = FileStorage(
        stream=io.BytesIO(b"%PDF-1.7 fake pdf"),
        filename="doc.pdf",
        content_type="application/pdf",
    )
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=7),
    ):
        response = await client.post("/d2/upload_image", files={"file": fake})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_upload_no_file_rejected(client):
    """POST без файла → 400."""
    await _login_gora_editor(client)
    with (
        _secretaries_mock({GORA_ADDRESS: {SECRETARY_ID}}),
        _user_org_names_mock({"GORA"}),
        _post_attachment_mock(row_id=7),
    ):
        response = await client.post("/d2/upload_image")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_img_serves_attachment_with_content_type(client):
    """Публичная отдача: bytes из Grist + content-type по магическим байтам."""
    rows = [{"id": 101, "FILE": 55, "ORG": "GORA"}]
    with (
        _d2_images_rows(rows),
        patch(
            "other.grist_tools.grist_manager.get_attachment",
            new=AsyncMock(return_value=PNG_BYTES),
        ) as get_mock,
    ):
        response = await client.get("/d2/img/101")

    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert await response.get_data() == PNG_BYTES
    assert get_mock.await_args.args[1] == 55
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"


@pytest.mark.asyncio
async def test_img_is_public(client):
    """Аноним (без сессии) читает картинку — публичный роут."""
    rows = [{"id": 101, "FILE": 55, "ORG": "GORA"}]
    with (
        _d2_images_rows(rows),
        patch(
            "other.grist_tools.grist_manager.get_attachment",
            new=AsyncMock(return_value=PNG_BYTES),
        ),
    ):
        response = await client.get("/d2/img/101")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_img_webp_sniffed(client):
    """webp (RIFF-контейнер) определяется по магическим байтам."""
    webp = b"RIFF\x24\x00\x00\x00WEBPVP8 fake"
    rows = [{"id": 5, "FILE": 6, "ORG": "GORA"}]
    with (
        _d2_images_rows(rows),
        patch(
            "other.grist_tools.grist_manager.get_attachment",
            new=AsyncMock(return_value=webp),
        ),
    ):
        response = await client.get("/d2/img/5")
    assert response.status_code == 200
    assert response.content_type == "image/webp"


@pytest.mark.asyncio
async def test_img_unknown_row_404(client):
    """Нет такой строки D2_IMAGES → 404."""
    with _d2_images_rows([]):
        response = await client.get("/d2/img/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_img_row_without_attachment_404(client):
    """Строка без FILE (attachment id не число) → 404."""
    rows = [{"id": 102, "FILE": "", "ORG": "GORA"}]
    with (
        _d2_images_rows(rows),
        patch(
            "other.grist_tools.grist_manager.get_attachment",
            new=AsyncMock(return_value=PNG_BYTES),
        ) as get_mock,
    ):
        response = await client.get("/d2/img/102")
    assert response.status_code == 404
    get_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_img_file_as_list_of_ids(client):
    """Grist возвращает attachment-колонку списком [id] — тоже работает."""
    rows = [{"id": 104, "FILE": [77], "ORG": "GORA"}]
    with (
        _d2_images_rows(rows),
        patch(
            "other.grist_tools.grist_manager.get_attachment",
            new=AsyncMock(return_value=PNG_BYTES),
        ) as get_mock,
    ):
        response = await client.get("/d2/img/104")
    assert response.status_code == 200
    assert get_mock.await_args.args[1] == 77


@pytest.mark.asyncio
async def test_img_attachment_download_failure_404(client):
    """Grist не отдал attachment → 404."""
    rows = [{"id": 103, "FILE": 66, "ORG": "GORA"}]
    with (
        _d2_images_rows(rows),
        patch(
            "other.grist_tools.grist_manager.get_attachment",
            new=AsyncMock(side_effect=Exception("grist down")),
        ),
    ):
        response = await client.get("/d2/img/103")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_img_file_as_celldref_list(client):
    """Реальный Grist отдаёт FILE как ['L', 4] (CelldRef: тип + число).
    Регрессия-2026-10-11: file_ref[0]='L' давал 404 при живой картинке."""
    rows = [{"id": 105, "FILE": ["L", 88], "ORG": "GORA"}]
    with (
        _d2_images_rows(rows),
        patch(
            "other.grist_tools.grist_manager.get_attachment",
            new=AsyncMock(return_value=PNG_BYTES),
        ) as get_mock,
    ):
        response = await client.get("/d2/img/105")
    assert response.status_code == 200
    assert get_mock.await_args.args[1] == 88
