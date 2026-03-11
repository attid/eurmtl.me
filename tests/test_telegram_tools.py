import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from other.telegram_tools import (
    check_response,
    check_response_webapp,
    edit_telegram_message_,
    is_hash_valid,
    is_user_admin,
    prepare_data_check_string,
    prepare_html_text,
    send_telegram_message_,
)


@pytest.mark.asyncio
async def test_send_and_edit_telegram_message_helpers():
    with patch(
        "other.telegram_tools.http_session_manager.get_web_request",
        AsyncMock(
            side_effect=[
                SimpleNamespace(status=200, data={"result": {"message_id": 77}}),
                SimpleNamespace(status=500, data="error"),
                SimpleNamespace(status=200, data={"ok": True}),
                Exception("boom"),
            ]
        ),
    ):
        assert await send_telegram_message_(1, "hello") == 77
        assert await send_telegram_message_(1, "hello") is None
        assert await edit_telegram_message_(1, 2, "text") is True
        assert await edit_telegram_message_(1, 2, "text") is False


@pytest.mark.asyncio
async def test_is_user_admin_formats_chat_id_and_handles_failure():
    ok = SimpleNamespace(status=200, data={"result": {"status": "administrator"}})
    fail = SimpleNamespace(status=500, data={"error": "bad"})

    with patch(
        "other.telegram_tools.http_session_manager.get_web_request",
        AsyncMock(side_effect=[ok, fail]),
    ) as get_request:
        assert await is_user_admin(12345, 7) is True
        assert await is_user_admin("-10012345", 7) is False

    first_url = get_request.await_args_list[0].args[1]
    assert "chat_id=-10012345" in first_url


def test_check_response_and_webapp_helpers():
    token = "token123"
    data = {"auth_date": "1", "query_id": "q", "user": "u"}
    data_string = "auth_date=1\nquery_id=q\nuser=u".encode("utf-8")
    secret = hashlib.sha256(token.encode("utf-8")).digest()
    valid_hash = hmac.new(secret, data_string, hashlib.sha256).hexdigest()

    assert check_response({**data, "hash": valid_hash}, token=token) is True
    assert check_response({**data, "hash": "bad"}, token=token) is False

    query = "query_id=q&user=u&auth_date=1&hash=abc"
    hash_value, check_string = prepare_data_check_string(query)
    assert hash_value == "abc"
    assert check_string == "auth_date=1\nquery_id=q\nuser=u"

    web_token = "web-token"
    web_secret = hmac.new(
        b"WebAppData", web_token.encode("utf-8"), hashlib.sha256
    ).digest()
    valid_web_hash = hmac.new(
        web_secret,
        check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert is_hash_valid(valid_web_hash, check_string, web_token) is True
    assert is_hash_valid("bad", check_string, web_token) is False

    assert (
        check_response_webapp(
            query.replace("hash=abc", f"hash={valid_web_hash}"),
            config_token=SecretStr(web_token),
        )
        is True
    )


def test_prepare_html_text_replaces_tags_and_validates_type():
    assert prepare_html_text("<p>Hello</p>") == "<div>Hello</div>"
    with pytest.raises(TypeError, match="Input must be a string"):
        prepare_html_text(None)
