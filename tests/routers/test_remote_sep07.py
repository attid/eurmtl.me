import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_remote_sep07_success(client):
    """Test successful submission of XDR"""
    valid_xdr = "AAAAAA=="  # Valid Base64
    mock_service_result = {
        "SUCCESS": True,
        "hash": "test_hash_123",
        "MESSAGES": ["Added signature"],
    }

    # Patch TransactionService in the module where it is used (routers.remote_sep07)
    # We patch the class so that when it's instantiated, it returns our mock
    with patch("routers.remote_sep07.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.sign_transaction_from_xdr = AsyncMock(
            return_value=mock_service_result
        )

        response = await client.post("/remote/sep07", form={"xdr": valid_xdr})

        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "pending"
        assert data["hash"] == "test_hash_123"


@pytest.mark.asyncio
async def test_remote_sep07_invalid_base64(client):
    """Test submission of invalid Base64"""
    invalid_xdr = "NotBase64!"

    response = await client.post("/remote/sep07", form={"xdr": invalid_xdr})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["status"] == "failed"
    assert "Invalid or missing base64" in data["error"]["message"]


@pytest.mark.asyncio
async def test_remote_sep07_missing_xdr(client):
    """Test submission with missing XDR"""
    response = await client.post("/remote/sep07", form={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["status"] == "failed"


@pytest.mark.asyncio
async def test_remote_sep07_service_failure(client):
    """Test when service returns failure (e.g. transaction not found)"""
    valid_xdr = "AAAAAA=="
    mock_service_result = {
        "SUCCESS": False,
        "hash": "",
        "MESSAGES": ["Transaction not found"],
    }

    with patch("routers.remote_sep07.TransactionService") as MockService:
        mock_instance = MockService.return_value
        mock_instance.sign_transaction_from_xdr = AsyncMock(
            return_value=mock_service_result
        )

        response = await client.post("/remote/sep07", form={"xdr": valid_xdr})

        assert response.status_code == 404
        data = await response.get_json()
        assert data["status"] == "failed"
        assert "Transaction not found" in data["error"]["message"]


@pytest.mark.asyncio
async def test_remote_sep07_add_missing_uri(client):
    response = await client.post("/remote/sep07/add", json={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "Missing URI"


@pytest.mark.asyncio
async def test_remote_sep07_get_returns_404_for_unknown_uri(client):
    response = await client.get("/remote/sep07/get/missing")

    assert response.status_code == 404
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "URI not found"


@pytest.mark.asyncio
async def test_remote_sep07_parse_uri_requires_uri(client):
    response = await client.post("/remote/sep07/parse-uri", json={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "URI is required"


@pytest.mark.asyncio
async def test_remote_sep07_parse_uri_requires_xdr_param(client):
    response = await client.post(
        "/remote/sep07/parse-uri",
        json={"uri": "web+stellar:tx?callback=url:https://example.com/callback"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "No XDR found in URI"


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_requires_payload(client):
    response = await client.post("/remote/sep07/submit-signed", json={})

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "signed_xdr and callback_url are required"


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_validates_base64(client):
    response = await client.post(
        "/remote/sep07/submit-signed",
        json={"signed_xdr": "not-base64", "callback_url": "https://example.com"},
    )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "Invalid signed XDR format"


# --- Анти-SSRF защита callback-URL (инцидент #88 / Sentry #3121) ---


class _FakeCallbackResponse:
    """Минимальная замена aiohttp-ответа callback-сервера."""

    def __init__(self, status=200, body="ok", location=None):
        self.status = status
        self.headers = {"Location": location} if location else {}
        self._body = body

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _fake_session(handler):
    """Подмена aiohttp.ClientSession; handler(method, url) -> ответ/исключение.

    Исключение можно бросить прямо из ``handler`` — тогда оно возникнет
    при вызове ``session.get/post``, как у настоящего aiohttp.
    """

    class _FakeSession:
        last_init_kwargs = {}
        calls = []

        def __init__(self, *args, **kwargs):
            _FakeSession.last_init_kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            connector = _FakeSession.last_init_kwargs.get("connector")
            close = getattr(connector, "close", None)
            if close is not None:
                await close()
            return False

        def get(self, url, **kwargs):
            _FakeSession.calls.append(("GET", url))
            return handler("GET", url)

        def post(self, url, **kwargs):
            _FakeSession.calls.append(("POST", url))
            return handler("POST", url)

    return _FakeSession


def _raising(error):
    """handler для _fake_session: бросает исключение при запросе."""

    def handler(method, url):
        raise error

    return handler


def _connector_error(os_error: OSError) -> Exception:
    import aiohttp
    from aiohttp.client_reqrep import ConnectionKey

    key = ConnectionKey(
        host="rebind.attacker.example",
        port=443,
        is_ssl=True,
        ssl=True,
        proxy=None,
        proxy_auth=None,
        proxy_headers_hash=None,
    )
    return aiohttp.ClientConnectorDNSError(key, os_error)


async def _post_submit_signed(client, callback_url):
    return await client.post(
        "/remote/sep07/submit-signed",
        json={"signed_xdr": "AAAAAA==", "callback_url": callback_url},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback_url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:2019/config/",
        "http://10.0.0.5/callback",
        "http://172.17.0.1:2375/containers/json",
        "http://192.168.1.10/callback",
        "http://[fe80::1]:8080/callback",
        "http://localhost:2019/config/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://2130706433/callback",
    ],
)
async def test_remote_sep07_submit_signed_blocks_internal_callback(
    client, callback_url
):
    with patch("aiohttp.ClientSession") as mock_session:
        response = await _post_submit_signed(client, callback_url)

    assert response.status_code == 400
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert data["message"] == "callback URL is not allowed"
    mock_session.assert_not_called()


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_blocks_dns_rebinding(client):
    with (
        patch(
            "other.url_safety.resolve_host_ips", AsyncMock(return_value=["10.1.2.3"])
        ),
        patch("aiohttp.ClientSession") as mock_session,
    ):
        response = await _post_submit_signed(
            client, "https://rebind.attacker.example/callback"
        )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["message"] == "callback URL is not allowed"
    mock_session.assert_not_called()


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_blocks_private_ip_at_connect_time(client):
    from other.url_safety import CallbackURLNotAllowed

    error = _connector_error(CallbackURLNotAllowed("blocked at connect"))
    session_class = _fake_session(_raising(error))

    with (
        patch(
            "other.url_safety.resolve_host_ips",
            AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(
            client, "https://rebind.attacker.example/callback"
        )

    assert response.status_code == 400
    data = await response.get_json()
    assert data["message"] == "callback URL is not allowed"


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_keeps_500_for_other_connect_errors(client):
    error = _connector_error(OSError("connection refused"))
    session_class = _fake_session(_raising(error))

    with (
        patch(
            "other.url_safety.resolve_host_ips",
            AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(client, "https://example.com/callback")

    assert response.status_code == 500
    data = await response.get_json()
    assert data["SUCCESS"] is False


@pytest.mark.asyncio
async def test_remote_sep07_submit_signed_external_https_callback_works(client):
    import aiohttp

    from other.url_safety import SafeResolver

    session_class = _fake_session(
        lambda method, url: _FakeCallbackResponse(200, "accepted")
    )

    with (
        patch(
            "other.url_safety.resolve_host_ips",
            AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(client, "https://example.com/callback")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["SUCCESS"] is True
    assert data["callback_response"] == "accepted"

    # В сессию передаётся коннектор с валидирующим резолвером.
    connector = session_class.last_init_kwargs["connector"]
    assert isinstance(connector, aiohttp.TCPConnector)
    assert isinstance(getattr(connector, "_resolver", None), SafeResolver)


# --- Редиректы callback-сервера не должны обходить анти-SSRF ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,location",
    [
        # 302/307 с metadata: 307/308 сохраняют POST и тело
        (302, "http://169.254.169.254/latest/meta-data/"),
        (307, "http://169.254.169.254/latest/meta-data/"),
        (308, "http://169.254.169.254/latest/meta-data/"),
        # loopback admin API
        (302, "http://127.0.0.1:2019/config/"),
        (307, "http://127.0.0.1:2019/config/"),
        # RFC1918
        (301, "http://172.17.0.1:2375/containers/json"),
        (303, "http://192.168.1.10/callback"),
        (307, "http://10.0.0.5/callback"),
        # IPv6 link-local (в Location без скобок и со скобками)
        (307, "http://[fe80::1]:8080/callback"),
        # protocol-relative и userinfo не обходят проверку хоста
        (302, "//169.254.169.254/latest/meta-data/"),
        (302, "http://169.254.169.254@127.0.0.1:2019/config/"),
        # внутреннее имя и небезопасная схема
        (302, "http://localhost:2019/config/"),
        (302, "file:///etc/passwd"),
    ],
)
async def test_remote_sep07_redirect_to_internal_target_is_blocked(
    client, status, location
):
    session_class = _fake_session(
        lambda method, url: _FakeCallbackResponse(status, "redirect", location)
    )

    with (
        patch(
            "other.url_safety.resolve_host_ips",
            AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(client, "https://example.com/callback")

    assert response.status_code == 400
    data = await response.get_json()
    assert data["message"] == "callback URL is not allowed"

    # Внутренний адрес не запрашивался: был только первый (внешний) хоп.
    assert len(session_class.calls) == 1
    assert session_class.calls[0] == ("POST", "https://example.com/callback")


@pytest.mark.asyncio
async def test_remote_sep07_redirect_to_private_dns_name_is_blocked(client):
    """Location резолвится в private IP (DNS rebinding на редиректе)."""

    async def resolve(hostname, port):
        if hostname == "rebind.attacker.example":
            return ["10.1.2.3"]
        return ["93.184.216.34"]

    session_class = _fake_session(
        lambda method, url: (
            _FakeCallbackResponse(307, "redirect", "https://rebind.attacker.example/cb")
            if url == "https://example.com/callback"
            else _FakeCallbackResponse(200, "leaked")
        )
    )

    with (
        patch("other.url_safety.resolve_host_ips", AsyncMock(side_effect=resolve)),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(client, "https://example.com/callback")

    assert response.status_code == 400
    data = await response.get_json()
    assert data["message"] == "callback URL is not allowed"
    assert len(session_class.calls) == 1


@pytest.mark.asyncio
async def test_remote_sep07_redirect_307_to_external_https_preserves_post(client):
    session_class = _fake_session(
        lambda method, url: (
            _FakeCallbackResponse(307, "redirect", "https://other.example/cb")
            if url == "https://example.com/callback"
            else _FakeCallbackResponse(200, "accepted")
        )
    )

    with (
        patch(
            "other.url_safety.resolve_host_ips",
            AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(client, "https://example.com/callback")

    assert response.status_code == 200
    data = await response.get_json()
    assert data["SUCCESS"] is True
    assert data["callback_response"] == "accepted"
    assert session_class.calls == [
        ("POST", "https://example.com/callback"),
        ("POST", "https://other.example/cb"),
    ]


@pytest.mark.asyncio
async def test_remote_sep07_redirect_302_to_external_switches_to_get(client):
    session_class = _fake_session(
        lambda method, url: (
            _FakeCallbackResponse(302, "redirect", "/cb-done")
            if url == "https://example.com/callback"
            else _FakeCallbackResponse(200, "accepted")
        )
    )

    with (
        patch(
            "other.url_safety.resolve_host_ips",
            AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(client, "https://example.com/callback")

    assert response.status_code == 200
    # Относительный Location разрешён относительно текущего URL.
    assert session_class.calls == [
        ("POST", "https://example.com/callback"),
        ("GET", "https://example.com/cb-done"),
    ]


@pytest.mark.asyncio
async def test_remote_sep07_redirect_loop_is_limited(client):
    session_class = _fake_session(
        lambda method, url: _FakeCallbackResponse(
            307, "redirect", "https://example.com/callback"
        )
    )

    with (
        patch(
            "other.url_safety.resolve_host_ips",
            AsyncMock(return_value=["93.184.216.34"]),
        ),
        patch("aiohttp.ClientSession", session_class),
    ):
        response = await _post_submit_signed(client, "https://example.com/callback")

    assert response.status_code == 500
    data = await response.get_json()
    assert data["SUCCESS"] is False
    assert "redirect" in data["message"].lower()
