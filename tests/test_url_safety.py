"""Anti-SSRF проверки callback-URL (инцидент #88, Sentry #3121)."""

import socket
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp.resolver import DefaultResolver

from other import url_safety
from other.url_safety import (
    CallbackURLNotAllowed,
    SafeResolver,
    create_safe_connector,
    is_blocked_hostname,
    is_blocked_ip,
    normalize_hostname,
    validate_callback_url,
)


@pytest.mark.parametrize(
    "address",
    [
        # cloud metadata / IPv4 link-local
        "169.254.169.254",
        # loopback
        "127.0.0.1",
        "127.1.2.3",
        # RFC1918
        "10.0.0.1",
        "10.255.255.254",
        "172.16.0.1",
        "172.17.0.1",
        "172.31.255.255",
        "192.168.0.1",
        "192.168.255.255",
        # прочее немаршрутизируемое
        "0.0.0.0",
        "100.64.0.1",
        # IPv6 loopback / link-local / ULA
        "::1",
        "fe80::1",
        "fd00::1",
        # IPv4-mapped IPv6 не обходит проверку
        "::ffff:169.254.169.254",
        "::ffff:127.0.0.1",
        # невалидный адрес — fail-closed
        "not-an-ip",
    ],
)
def test_is_blocked_ip_blocks_internal(address):
    assert is_blocked_ip(address) is True


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "93.184.216.34",
        "172.15.0.1",  # вне 172.16.0.0/12
        "2606:4700::1111",
        "2a00:1450:4001:82f::200e",
    ],
)
def test_is_blocked_ip_allows_public(address):
    assert is_blocked_ip(address) is False


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "LOCALHOST",
        "localhost.",
        "api.localhost",
        "metadata",
        "metadata.google.internal",
        "printer.local",
        "service.internal",
        "router.lan",
        "nas.home.arpa",
        "intranet",  # односоставное имя
        "2130706433",  # decimal-форма 127.0.0.1
        "",
    ],
)
def test_is_blocked_hostname_blocks_internal(hostname):
    assert is_blocked_hostname(hostname) is True


@pytest.mark.parametrize(
    "hostname",
    ["example.com", "callback.example.com", "eurmtl.me", "8.8.8.8", "fe80::1"],
)
def test_is_blocked_hostname_allows_public(hostname):
    assert is_blocked_hostname(hostname) is False


def test_normalize_hostname():
    assert normalize_hostname("[FE80::1%25eth0].") == "fe80::1"


@pytest.mark.asyncio
async def test_validate_blocks_metadata_ip():
    with pytest.raises(CallbackURLNotAllowed):
        await validate_callback_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_validate_blocks_loopback_with_port():
    with pytest.raises(CallbackURLNotAllowed):
        await validate_callback_url("http://127.0.0.1:2019/config/")


@pytest.mark.asyncio
async def test_validate_blocks_ipv6_link_local():
    with pytest.raises(CallbackURLNotAllowed):
        await validate_callback_url("http://[fe80::1]:8080/callback")


@pytest.mark.asyncio
async def test_validate_blocks_hostname_resolving_to_private_ip():
    with patch.object(
        url_safety, "resolve_host_ips", AsyncMock(return_value=["10.1.2.3"])
    ):
        with pytest.raises(CallbackURLNotAllowed):
            await validate_callback_url("https://rebind.attacker.example/cb")


@pytest.mark.asyncio
async def test_validate_blocks_when_any_resolved_ip_is_private():
    with patch.object(
        url_safety,
        "resolve_host_ips",
        AsyncMock(return_value=["93.184.216.34", "192.168.1.1"]),
    ):
        with pytest.raises(CallbackURLNotAllowed):
            await validate_callback_url("https://mixed.attacker.example/cb")


@pytest.mark.asyncio
async def test_validate_blocks_unresolvable_host():
    with patch.object(
        url_safety, "resolve_host_ips", AsyncMock(side_effect=OSError("dns failed"))
    ):
        with pytest.raises(CallbackURLNotAllowed):
            await validate_callback_url("https://nxdomain.example/cb")


@pytest.mark.asyncio
async def test_validate_blocks_empty_dns_answer():
    with patch.object(url_safety, "resolve_host_ips", AsyncMock(return_value=[])):
        with pytest.raises(CallbackURLNotAllowed):
            await validate_callback_url("https://empty.example/cb")


@pytest.mark.asyncio
async def test_validate_allows_external_https():
    with patch.object(
        url_safety, "resolve_host_ips", AsyncMock(return_value=["93.184.216.34"])
    ):
        url = "https://example.com/callback"
        assert await validate_callback_url(url) == url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/callback",
        "file:///etc/passwd",
        "gopher://example.com/",
        "javascript:alert(1)",
        "http:///no-host",
    ],
)
async def test_validate_rejects_bad_scheme_or_missing_host(url):
    with patch.object(
        url_safety, "resolve_host_ips", AsyncMock(return_value=["93.184.216.34"])
    ):
        with pytest.raises(CallbackURLNotAllowed):
            await validate_callback_url(url)


@pytest.mark.asyncio
async def test_safe_resolver_blocks_private_dns_answer():
    resolver = SafeResolver()
    private = [
        {
            "hostname": "rebind.attacker.example",
            "host": "10.0.0.5",
            "port": 443,
            "family": socket.AF_INET,
            "proto": 0,
            "flags": 0,
        }
    ]
    with patch.object(DefaultResolver, "resolve", AsyncMock(return_value=private)):
        with pytest.raises(CallbackURLNotAllowed):
            await resolver.resolve("rebind.attacker.example", 443)


@pytest.mark.asyncio
async def test_safe_resolver_allows_public_dns_answer():
    resolver = SafeResolver()
    public = [
        {
            "hostname": "example.com",
            "host": "93.184.216.34",
            "port": 443,
            "family": socket.AF_INET,
            "proto": 0,
            "flags": 0,
        }
    ]
    with patch.object(DefaultResolver, "resolve", AsyncMock(return_value=public)):
        assert await resolver.resolve("example.com", 443) == public


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["localhost", "metadata.google.internal", "intranet"])
async def test_safe_resolver_blocks_internal_hostname_without_dns(host):
    resolver = SafeResolver()
    with patch.object(DefaultResolver, "resolve", AsyncMock(return_value=[])) as dns:
        with pytest.raises(CallbackURLNotAllowed):
            await resolver.resolve(host, 80)
    dns.assert_not_called()


@pytest.mark.asyncio
async def test_create_safe_connector_uses_validating_resolver():
    connector = create_safe_connector()
    try:
        assert isinstance(getattr(connector, "_resolver", None), SafeResolver)
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_safe_connector_blocks_private_ip_during_real_connect():
    """aiohttp оборачивает OSError резолвера в ClientConnectorDNSError."""
    import aiohttp

    private = [
        {
            "hostname": "rebind.attacker.example",
            "host": "127.0.0.1",
            "port": 9,
            "family": socket.AF_INET,
            "proto": 0,
            "flags": 0,
        }
    ]
    connector = create_safe_connector()
    try:
        with patch.object(DefaultResolver, "resolve", AsyncMock(return_value=private)):
            async with aiohttp.ClientSession(connector=connector) as session:
                with pytest.raises(aiohttp.ClientConnectorDNSError) as exc_info:
                    await session.get("http://rebind.attacker.example:9/callback")
    finally:
        await connector.close()

    assert isinstance(exc_info.value.os_error, CallbackURLNotAllowed)


@pytest.mark.asyncio
async def test_safe_connector_blocks_ip_literal_without_resolver():
    """aiohttp не зовёт резолвер для IP-литералов — коннектор проверяет сам."""
    import aiohttp

    connector = create_safe_connector()
    try:
        with patch.object(
            DefaultResolver,
            "resolve",
            AsyncMock(side_effect=AssertionError("resolver must not be used")),
        ):
            async with aiohttp.ClientSession(connector=connector) as session:
                with pytest.raises(aiohttp.ClientConnectorDNSError) as exc_info:
                    await session.get("http://127.0.0.1:9/callback")
    finally:
        await connector.close()

    assert isinstance(exc_info.value.os_error, CallbackURLNotAllowed)
