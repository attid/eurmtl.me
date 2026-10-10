"""GristAPI.post_attachment / get_attachment — контракты Grist Attachments API.

post_attachment:
  1) POST /docs/{docId}/attachments (multipart) → [N] или [{"id": N}];
  2) POST records → {"records": [{"id": row_id, ...}]}.
get_attachment:
  GET /docs/{docId}/attachments/{id}/download → bytes.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from other.grist_tools import GristAPI, GristTableConfig


@pytest.mark.asyncio
async def test_post_attachment_uploads_and_creates_record():
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(
            side_effect=[
                # Реальный Grist отвечает просто числом в списке: [55].
                SimpleNamespace(status=200, data=[55]),
                SimpleNamespace(
                    status=200,
                    data={"records": [{"id": 101, "fields": {"FILE": [55]}}]},
                ),
            ]
        )
    )
    api = GristAPI(session_manager=session_manager)
    table = GristTableConfig("doc", "D2_IMAGES")

    row_id = await api.post_attachment(
        table,
        b"\x89PNG\r\n\x1a\ndata",
        "pic.png",
        {"ORG": "GORA", "UPLOADED_BY": "@itolstov", "CREATED_AT": "2026-10-09"},
    )

    assert row_id == 101
    upload_call, record_call = session_manager.get_web_request.await_args_list
    assert (
        upload_call.kwargs["url"] == "https://grist.eurmtl.me/api/docs/doc/attachments"
    )
    assert upload_call.kwargs["method"] == "POST"
    assert upload_call.kwargs["data"] is not None  # multipart FormData
    record_payload = record_call.kwargs["json"]
    fields = record_payload["records"][0]["fields"]
    assert fields["FILE"] == 55
    assert fields["ORG"] == "GORA"
    assert fields["UPLOADED_BY"] == "@itolstov"


@pytest.mark.asyncio
async def test_post_attachment_accepts_dict_id_shape():
    """Документированная форма [{"id": N}] тоже разбирается."""
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(
            side_effect=[
                SimpleNamespace(status=200, data=[{"id": 66}]),
                SimpleNamespace(
                    status=200,
                    data={"records": [{"id": 102, "fields": {"FILE": [66]}}]},
                ),
            ]
        )
    )
    api = GristAPI(session_manager=session_manager)
    row_id = await api.post_attachment(
        GristTableConfig("doc", "D2_IMAGES"),
        b"data",
        "pic.png",
        {"ORG": "GORA"},
    )
    assert row_id == 102
    record_call = session_manager.get_web_request.await_args_list[1]
    assert record_call.kwargs["json"]["records"][0]["fields"]["FILE"] == 66


@pytest.mark.asyncio
async def test_post_attachment_upload_error_raises():
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(return_value=SimpleNamespace(status=401, data={}))
    )
    api = GristAPI(session_manager=session_manager)
    with pytest.raises(Exception, match="attachment"):
        await api.post_attachment(GristTableConfig("doc", "T"), b"x", "x.png", {})


@pytest.mark.asyncio
async def test_post_attachment_record_error_raises():
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(
            side_effect=[
                SimpleNamespace(status=200, data=[{"id": 55}]),
                SimpleNamespace(status=500, data={}),
            ]
        )
    )
    api = GristAPI(session_manager=session_manager)
    with pytest.raises(Exception, match="D2_IMAGES"):
        await api.post_attachment(
            GristTableConfig("doc", "D2_IMAGES"), b"x", "x.png", {}
        )


@pytest.mark.asyncio
async def test_get_attachment_downloads_bytes():
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(
            return_value=SimpleNamespace(status=200, data=b"file-bytes")
        )
    )
    api = GristAPI(session_manager=session_manager)

    data = await api.get_attachment(GristTableConfig("doc", "D2_IMAGES"), 55)

    assert data == b"file-bytes"
    call = session_manager.get_web_request.await_args
    assert call.kwargs["url"] == (
        "https://grist.eurmtl.me/api/docs/doc/attachments/55/download"
    )
    assert call.kwargs["method"] == "GET"
    assert call.kwargs["return_type"] == "bytes"


@pytest.mark.asyncio
async def test_get_attachment_error_raises():
    session_manager = SimpleNamespace(
        get_web_request=AsyncMock(return_value=SimpleNamespace(status=404, data=b""))
    )
    api = GristAPI(session_manager=session_manager)
    with pytest.raises(Exception, match="404"):
        await api.get_attachment(GristTableConfig("doc", "T"), 999)
