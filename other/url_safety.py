"""Анти-SSRF проверки для callback-URL, приходящих из внешних запросов.

Эндпоинты вроде ``POST /remote/sep07/submit-signed`` принимают URL из тела
запроса и делают на него исходящий POST. Без проверки это превращает
приложение в SSRF-прокси: можно прочитать cloud-metadata
(``169.254.169.254``) или просканировать внутренние порты.

Модуль даёт четыре уровня защиты:

1. :func:`is_blocked_ip` / :func:`is_blocked_hostname` — чистые проверки
   адреса и имени (без I/O).
2. :func:`validate_callback_url` — pre-flight проверка: схема, имя и все
   адреса из DNS-резолва.
3. :class:`SafeResolver` / :class:`SafeConnector` — проверка IP в момент
   установления соединения (защита от DNS rebinding: между pre-flight и
   connect DNS-ответ может измениться). IP-литералы aiohttp резолвером не
   прогоняет, поэтому их проверяет :class:`SafeConnector`.
4. :func:`post_callback` — ручная обработка редиректов: каждый ``Location``
   валидируется до запроса, редирект на private/metadata-адрес не
   выполняется (в т.ч. 307/308, сохраняющие POST).

Любая блокировка поднимает :class:`CallbackURLNotAllowed`, который роутер
превращает в HTTP 400 ``callback URL is not allowed``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import aiohttp
from aiohttp.abc import ResolveResult
from aiohttp.resolver import DefaultResolver

ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Статусы, которые aiohttp (и RFC 9110) считает редиректами.
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

#: Совпадает с дефолтом ``aiohttp.ClientSession``.
MAX_CALLBACK_REDIRECTS = 10

#: Сети, которые обязаны быть заблокированы независимо от того, как
#: конкретная версия Python трактует ``ipaddress.is_private``/``is_global``.
BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",  # unspecified / "this host"
        "10.0.0.0/8",  # RFC1918
        "100.64.0.0/10",  # CGNAT, tailscale и прочие немаршрутизируемые сети
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local + cloud metadata
        "172.16.0.0/12",  # RFC1918
        "192.168.0.0/16",  # RFC1918
        "::1/128",  # IPv6 loopback
        "fc00::/7",  # IPv6 unique local
        "fe80::/10",  # IPv6 link-local
    )
)

#: Имена, которые не могут быть публичным callback-адресом.
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "instance-data",
    }
)

#: Суффиксы внутренних DNS-зон (RFC 6761/6762, cloud-окружения).
BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home.arpa",
    ".lan",
    ".intranet",
)

#: Сколько ждём DNS-ответ на pre-flight проверку.
DNS_TIMEOUT = 5.0


class CallbackURLNotAllowed(OSError):
    """callback-URL ведёт во внутреннюю сеть или небезопасен.

    Наследуемся от ``OSError``: тот же класс исключения поднимает
    :class:`SafeResolver` внутри aiohttp, где другие типы не ожидаются.
    """


class CallbackRedirectLimitExceeded(RuntimeError):
    """callback-сервер отдал слишком длинную цепочку редиректов."""


@dataclass(frozen=True)
class CallbackResponse:
    """Финальный ответ callback-сервера после всех редиректов."""

    url: str
    status: int
    text: str


def normalize_hostname(hostname: str) -> str:
    """Приводит имя хоста к виду, удобному для сравнения."""
    host = (hostname or "").strip().lower().strip("[]")
    host = host.split("%", 1)[0]  # отбрасываем IPv6 zone id
    return host.rstrip(".")


def _parse_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address):
    """Возвращает ``ipaddress``-объект или ``None``, если это не IP."""
    text = str(value).strip("[]").split("%", 1)[0]
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        return None


def _is_blocked_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        # ::ffff:169.254.169.254 — это тот же metadata по IPv4.
        address = address.ipv4_mapped
    if any(address in network for network in BLOCKED_NETWORKS):
        return True
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )


def is_blocked_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True, если адрес не является публичным unicast (fail-closed)."""
    address = _parse_ip(value)
    if address is None:
        return True
    return _is_blocked_address(address)


def is_blocked_hostname(hostname: str) -> bool:
    """True, если имя хоста заведомо указывает во внутреннюю сеть.

    IP-литералы здесь не проверяются — для них есть :func:`is_blocked_ip`.
    """
    host = normalize_hostname(hostname)
    if not host:
        return True
    if host in BLOCKED_HOSTNAMES:
        return True
    if any(host.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES):
        return True
    if _parse_ip(host) is not None:
        return False
    # Односоставное имя (``metadata``, ``2130706433``, имя docker-сервиса)
    # в публичном DNS не существует — трактуем как внутреннее.
    return "." not in host


async def resolve_host_ips(hostname: str, port: int) -> list[str]:
    """Резолвит имя в список IP-адресов (с таймаутом)."""
    loop = asyncio.get_running_loop()
    infos = await asyncio.wait_for(
        loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM),
        timeout=DNS_TIMEOUT,
    )
    addresses: list[str] = []
    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        if address not in addresses:
            addresses.append(address)
    return addresses


async def validate_callback_url(url: str) -> str:
    """Проверяет URL перед исходящим запросом и возвращает его без изменений.

    :raises CallbackURLNotAllowed: схема/имя/адрес ведут не туда, либо
        DNS-резолв невозможен.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise CallbackURLNotAllowed(f"malformed callback URL: {exc}") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise CallbackURLNotAllowed(f"scheme {scheme!r} is not allowed")

    hostname = parts.hostname
    if not hostname:
        raise CallbackURLNotAllowed("callback URL has no host")

    if is_blocked_hostname(hostname):
        raise CallbackURLNotAllowed(f"host {hostname!r} is not allowed")

    address = _parse_ip(normalize_hostname(hostname))
    if address is not None:
        if _is_blocked_address(address):
            raise CallbackURLNotAllowed(f"address {address} is not allowed")
        return url

    resolved_port = port or (443 if scheme == "https" else 80)
    try:
        addresses = await resolve_host_ips(hostname, resolved_port)
    except (OSError, asyncio.TimeoutError) as exc:
        raise CallbackURLNotAllowed(f"cannot resolve host {hostname!r}: {exc}") from exc

    if not addresses:
        raise CallbackURLNotAllowed(f"host {hostname!r} resolved to no addresses")

    for resolved in addresses:
        if is_blocked_ip(resolved):
            raise CallbackURLNotAllowed(
                f"host {hostname!r} resolves to blocked address {resolved}"
            )
    return url


class SafeResolver(DefaultResolver):
    """Резолвер aiohttp, который не отдаёт приватные адреса.

    Проверка выполняется непосредственно перед connect, поэтому
    DNS rebinding (публичный IP на pre-flight, приватный на connect)
    не проходит. Исходное имя сохраняется в ``Host``/SNI — URL не
    переписывается.
    """

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        if is_blocked_hostname(host):
            raise CallbackURLNotAllowed(f"host {host!r} is not allowed")

        results = await super().resolve(host, port, family)
        for result in results:
            if is_blocked_ip(result["host"]):
                raise CallbackURLNotAllowed(
                    f"host {host!r} resolves to blocked address {result['host']}"
                )
        return results


class SafeConnector(aiohttp.TCPConnector):
    """Коннектор, который не соединяется с внутренними IP-литералами.

    ``SafeResolver`` покрывает DNS-имена, но aiohttp для IP-литералов
    возвращает адрес напрямую, минуя резолвер
    (``TCPConnector._resolve_host``). Проверка здесь — defense in depth к
    по-шаговой валидации в :func:`post_callback`.
    """

    async def _resolve_host(self, host: str, port: int, traces=None):
        address = _parse_ip(host)
        if address is not None and _is_blocked_address(address):
            raise CallbackURLNotAllowed(f"address {address} is not allowed")
        return await super()._resolve_host(host, port, traces=traces)


def create_safe_connector() -> aiohttp.TCPConnector:
    """Коннектор aiohttp с проверкой адреса в момент connect."""
    return SafeConnector(resolver=SafeResolver())


async def post_callback(
    callback_url: str,
    form_fields: Mapping[str, str],
    *,
    max_redirects: int = MAX_CALLBACK_REDIRECTS,
) -> CallbackResponse:
    """POST на callback-URL с ручной обработкой редиректов.

    Каждый адрес — исходный и каждый ``Location`` — проверяется
    :func:`validate_callback_url` **до** запроса, поэтому редирект на
    metadata/loopback/RFC1918/IPv6 link-local не выполняется даже для
    IP-литералов (307/308 сохраняют POST и тело).

    :raises CallbackURLNotAllowed: блокированный адрес на любом шаге.
    :raises CallbackRedirectLimitExceeded: больше ``max_redirects``
        редиректов.
    """
    url = await validate_callback_url(callback_url)
    method = "POST"
    redirects = 0

    async with aiohttp.ClientSession(connector=create_safe_connector()) as session:
        while True:
            if method == "GET":
                request = session.get(url, allow_redirects=False)
            else:
                form_data = aiohttp.FormData()
                for name, value in form_fields.items():
                    form_data.add_field(name, value)
                request = session.post(url, data=form_data, allow_redirects=False)

            async with request as response:
                status = response.status
                # aiohttp принимает и Location, и устаревший URI.
                location = response.headers.get("Location") or response.headers.get(
                    "URI"
                )
                if status not in REDIRECT_STATUSES or not location:
                    return CallbackResponse(url, status, await response.text())

            if redirects >= max_redirects:
                raise CallbackRedirectLimitExceeded(
                    f"more than {max_redirects} redirects from {callback_url!r}"
                )
            redirects += 1

            url = await validate_callback_url(urljoin(url, location))
            # Семантика aiohttp: 301/302 после POST и 303 всегда → GET без
            # тела; 307/308 сохраняют метод и тело.
            if status in (301, 302, 303):
                method = "GET"
