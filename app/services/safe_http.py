"""SSRF-hardened outbound HTTP client.

Several compare engines and a couple of routes issue HTTP requests to a URL
that the API caller controls (``/api/compare`` plain-text/self-peer/azure
targets, ``/api/peer-models``, and the ``urlSource`` analyze input). Without
guarding, a remote caller can make the server reach loopback, private,
link-local, or other internal destinations and read the response back
(CWE-918).

This module centralises a hardened ``httpx.AsyncClient`` factory:

* only ``http``/``https`` schemes are allowed,
* the target host is resolved and **every** resolved address must be a global
  (public) unicast address,
* the request is pinned to the validated address before connecting, so a DNS
  rebinding race cannot swap in an internal address between check and connect,
* redirects are revalidated through the same transport (and are not followed by
  default), and
* IPv4-mapped IPv6 addresses are unwrapped before classification.

Operators who legitimately need to reach internal targets (e.g. comparing
against another docread instance on the same LAN/Docker network) can opt in via
``OUTBOUND_ALLOW_HOSTS`` (comma-separated hostnames and/or CIDRs) or, as a blunt
escape hatch, ``OUTBOUND_ALLOW_PRIVATE=true``.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator, Sequence
from typing import cast

import httpx

from app.config import get_settings

_IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
_IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class SSRFError(httpx.RequestError):
    """Raised when an outbound request targets a disallowed address.

    Subclasses ``httpx.RequestError`` so existing ``except httpx.HTTPError``
    handlers translate it into a client/gateway error instead of a 500.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _parse_allow(items: Sequence[str] | None) -> tuple[set[str], list[_IpNetwork]]:
    """Split an allow list into literal hostnames and IP networks."""
    hostnames: set[str] = set()
    networks: list[_IpNetwork] = []
    for raw in items or ():
        item = raw.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            hostnames.add(item.lower())
    return hostnames, networks


def _unwrap(ip: _IpAddress) -> _IpAddress:
    """Unwrap IPv4-mapped IPv6 addresses (``::ffff:127.0.0.1``)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_blocked(ip: _IpAddress) -> bool:
    """True for any non-global / internal address class."""
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class _LimitedAsyncStream(httpx.AsyncByteStream):
    """Wrap a response stream and abort once it exceeds ``limit`` bytes."""

    def __init__(self, stream: httpx.AsyncByteStream, limit: int) -> None:
        self._stream = stream
        self._limit = limit

    async def __aiter__(self) -> AsyncIterator[bytes]:
        total = 0
        async for chunk in self._stream:
            total += len(chunk)
            if total > self._limit:
                raise SSRFError(f"Outbound response exceeded the {self._limit}-byte limit.")
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


async def _resolve(host: str, port: int) -> list[str]:
    """Resolve ``host`` to the set of distinct IP strings it maps to."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve host {host!r}: {exc}") from exc
    seen: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.append(addr)
    return seen


class SafeTransport(httpx.AsyncHTTPTransport):
    """httpx transport that blocks SSRF before each (redirect) request."""

    def __init__(
        self,
        *,
        allow_hosts: Sequence[str] | None = None,
        allow_private: bool = False,
        max_response_bytes: int | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._allow_hostnames, self._allow_networks = _parse_allow(allow_hosts)
        self._allow_private = allow_private
        self._max_response_bytes = max_response_bytes

    def _ip_allowed(self, ip: _IpAddress) -> bool:
        check = _unwrap(ip)
        for net in self._allow_networks:
            if check.version == net.version and check in net:
                return True
            if ip.version == net.version and ip in net:
                return True
        if self._allow_private:
            return True
        return not _is_blocked(check)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.scheme not in ("http", "https"):
            raise SSRFError(f"Blocked URL scheme {url.scheme!r}; only http/https are allowed.")
        host = url.host
        if not host:
            raise SSRFError("Blocked request with an empty host.")

        # Operator-trusted hostname: connect as-is without IP pinning.
        if host.lower() in self._allow_hostnames:
            return await super().handle_async_request(request)

        port = url.port or (443 if url.scheme == "https" else 80)
        safe_ip: str | None = None
        for addr in await _resolve(host, port):
            ip = ipaddress.ip_address(addr)
            if not self._ip_allowed(ip):
                raise SSRFError(
                    f"Blocked outbound request to non-public address {addr} for host {host!r}."
                )
            if safe_ip is None:
                safe_ip = addr
        if safe_ip is None:
            raise SSRFError(f"Could not resolve host {host!r} to a permitted address.")

        # Pin to the validated address; keep the original Host header (already
        # set on the request) and force TLS SNI/verification to use the
        # hostname rather than the literal IP we connect to.
        request.url = url.copy_with(host=safe_ip)
        request.extensions = {**request.extensions, "sni_hostname": host}
        response = await super().handle_async_request(request)
        return self._limit_response(response)

    def _limit_response(self, response: httpx.Response) -> httpx.Response:
        if self._max_response_bytes is None or self._max_response_bytes <= 0:
            return response
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max_response_bytes:
            raise SSRFError(
                f"Outbound response exceeded the {self._max_response_bytes}-byte limit."
            )
        stream = cast(httpx.AsyncByteStream, response.stream)
        response.stream = _LimitedAsyncStream(stream, self._max_response_bytes)
        return response


def create_safe_async_client(
    *,
    verify: bool = True,
    timeout: float = 60.0,
    follow_redirects: bool = False,
    allow_hosts: Sequence[str] | None = None,
    allow_private: bool | None = None,
    max_response_bytes: int | None = None,
) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` that rejects SSRF targets.

    ``allow_hosts`` / ``allow_private`` / ``max_response_bytes`` default to the
    values from :func:`app.config.get_settings` when not provided, so callers
    normally do not have to thread operator configuration through every engine.
    """
    if allow_hosts is None or allow_private is None or max_response_bytes is None:
        settings = get_settings()
        if allow_hosts is None:
            allow_hosts = settings.outbound_allow_hosts
        if allow_private is None:
            allow_private = settings.outbound_allow_private
        if max_response_bytes is None:
            max_response_bytes = settings.outbound_max_response_bytes
    transport = SafeTransport(
        verify=verify,
        allow_hosts=allow_hosts,
        allow_private=allow_private,
        max_response_bytes=max_response_bytes,
    )
    return httpx.AsyncClient(
        timeout=timeout,
        transport=transport,
        follow_redirects=follow_redirects,
    )


__all__ = ["SSRFError", "SafeTransport", "create_safe_async_client"]
