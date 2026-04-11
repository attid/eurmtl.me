import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from other.telegram_tools import (
    check_response,
    check_response_webapp,
    is_hash_valid,
    is_user_admin,
    prepare_data_check_string,
    prepare_html_text,
)


@pytest.mark.asyncio
async def test_is_user_admin_formats_chat_id_and_handles_failure():
    get_member = AsyncMock(
        side_effect=[
            SimpleNamespace(status="administrator"),
            RuntimeError("boom"),
        ]
    )
    with patch("other.telegram_tools.skynet_bot.get_chat_member", get_member):
        assert await is_user_admin(12345, 7) is True
        assert await is_user_admin("-10012345", 7) is False

    first_kwargs = get_member.await_args_list[0].kwargs
    assert first_kwargs["chat_id"] == "-10012345"
    second_kwargs = get_member.await_args_list[1].kwargs
    assert second_kwargs["chat_id"] == "-10012345"


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
