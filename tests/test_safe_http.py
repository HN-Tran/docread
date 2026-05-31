"""SSRF guard regression tests for the shared outbound HTTP client.

Covers the address classes the security report called out: loopback, RFC1918
private ranges, link-local (incl. the cloud metadata IP), IPv6 loopback,
IPv4-mapped IPv6, DNS names that resolve into private space, non-http(s)
schemes, and per-hop revalidation. Also covers the operator opt-in allow list.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Sequence
from typing import Any, TypeVar

import httpx
import pytest

from app.services import safe_http
from app.services.safe_http import SafeTransport, SSRFError, create_safe_async_client

T = TypeVar("T")


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


def _patch_resolve(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, list[str]]) -> None:
    async def fake_resolve(host: str, port: int) -> list[str]:
        if host in mapping:
            return mapping[host]
        raise SSRFError(f"no mapping for {host!r}")

    monkeypatch.setattr(safe_http, "_resolve", fake_resolve)


def _patch_parent(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_handle(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        captured["url"] = request.url
        captured["sni_hostname"] = request.extensions.get("sni_hostname")
        captured["host_header"] = request.headers.get("host")
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)
    return captured


async def _get(
    url: str,
    *,
    allow_hosts: Sequence[str] = (),
    allow_private: bool = False,
) -> httpx.Response:
    async with create_safe_async_client(
        allow_hosts=allow_hosts, allow_private=allow_private
    ) as client:
        return await client.get(url)


@pytest.mark.parametrize(
    "addr",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # RFC1918
        "192.168.1.10",  # RFC1918
        "172.16.0.1",  # RFC1918
        "169.254.169.254",  # link-local / cloud metadata
        "0.0.0.0",  # unspecified
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "fc00::1",  # IPv6 unique-local
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 loopback
        "::ffff:10.0.0.1",  # IPv4-mapped IPv6 private
    ],
)
def test_blocks_internal_addresses(monkeypatch: pytest.MonkeyPatch, addr: str) -> None:
    _patch_resolve(monkeypatch, {"target.test": [addr]})
    _patch_parent(monkeypatch)
    with pytest.raises(SSRFError):
        _run(_get("http://target.test/x"))


def test_blocks_dns_name_resolving_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    # A public-looking hostname that resolves into RFC1918 must be rejected.
    _patch_resolve(monkeypatch, {"sneaky.example.com": ["10.10.10.10"]})
    _patch_parent(monkeypatch)
    with pytest.raises(SSRFError):
        _run(_get("https://sneaky.example.com/data"))


def test_blocks_when_any_resolved_address_is_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mixed answer (one public, one private) must be rejected, not partially allowed.
    _patch_resolve(monkeypatch, {"mixed.test": ["93.184.216.34", "10.0.0.1"]})
    _patch_parent(monkeypatch)
    with pytest.raises(SSRFError):
        _run(_get("http://mixed.test/"))


def test_blocks_non_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_parent(monkeypatch)
    transport = SafeTransport(allow_hosts=(), allow_private=False)
    request = httpx.Request("GET", "file:///etc/passwd")
    with pytest.raises(SSRFError):
        _run(transport.handle_async_request(request))


def test_allows_public_address_and_pins_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, {"good.example.com": ["93.184.216.34"]})
    captured = _patch_parent(monkeypatch)
    resp = _run(_get("http://good.example.com/path"))
    assert resp.status_code == 200
    # Pinned to the validated IP so a DNS rebind cannot swap in an internal host.
    assert captured["url"].host == "93.184.216.34"
    # TLS SNI / Host header still carry the original hostname.
    assert captured["sni_hostname"] == "good.example.com"
    assert captured["host_header"] == "good.example.com"


def test_allows_public_ipv6_and_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, {"v6.example.com": ["2606:2800:220:1:248:1893:25c8:1946"]})
    captured = _patch_parent(monkeypatch)
    resp = _run(_get("https://v6.example.com/"))
    assert resp.status_code == 200
    assert captured["url"].host == "2606:2800:220:1:248:1893:25c8:1946"


def test_allow_hosts_hostname_bypasses_ip_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    # Operator-trusted hostname is allowed without even resolving it.
    def boom(host: str, port: int) -> list[str]:
        raise AssertionError("allowlisted hostname should not be resolved")

    monkeypatch.setattr(safe_http, "_resolve", boom)
    captured = _patch_parent(monkeypatch)
    resp = _run(_get("http://ocr.internal/api", allow_hosts=("ocr.internal",)))
    assert resp.status_code == 200
    assert captured["url"].host == "ocr.internal"


def test_allow_hosts_cidr_permits_private_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, {"peer.test": ["172.17.0.5"]})
    captured = _patch_parent(monkeypatch)
    resp = _run(_get("http://peer.test/api", allow_hosts=("172.17.0.0/16",)))
    assert resp.status_code == 200
    assert captured["url"].host == "172.17.0.5"


def test_allow_private_escape_hatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, {"localhost": ["127.0.0.1"]})
    captured = _patch_parent(monkeypatch)
    resp = _run(_get("http://localhost:11434/api", allow_private=True))
    assert resp.status_code == 200
    assert captured["url"].host == "127.0.0.1"


def test_redirect_hop_to_internal_is_revalidated(monkeypatch: pytest.MonkeyPatch) -> None:
    # httpx re-invokes the transport for each redirect hop, so a redirect that
    # lands on an internal address is rejected exactly like a direct request.
    _patch_resolve(monkeypatch, {"redir.test": ["10.0.0.9"]})
    _patch_parent(monkeypatch)
    transport = SafeTransport(allow_hosts=(), allow_private=False)
    redirected = httpx.Request("GET", "http://redir.test/internal")
    with pytest.raises(SSRFError):
        _run(transport.handle_async_request(redirected))


class _FakeStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


def test_blocks_oversized_response_via_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, {"big.example.com": ["93.184.216.34"]})

    async def fake_handle(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 100)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)

    async def go() -> None:
        async with create_safe_async_client(
            allow_hosts=(), allow_private=False, max_response_bytes=10
        ) as client:
            await client.get("http://big.example.com/")

    with pytest.raises(SSRFError):
        _run(go())


def test_blocks_oversized_streamed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, {"stream.example.com": ["93.184.216.34"]})

    async def fake_handle(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        # No content-length header -> the streamed byte cap must catch it.
        return httpx.Response(200, stream=_FakeStream([b"x" * 8, b"x" * 8]))

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)

    async def go() -> None:
        async with create_safe_async_client(
            allow_hosts=(), allow_private=False, max_response_bytes=10
        ) as client:
            await client.get("http://stream.example.com/")

    with pytest.raises(SSRFError):
        _run(go())


def test_response_within_limit_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, {"ok.example.com": ["93.184.216.34"]})

    async def fake_handle(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"small")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_handle)

    async def go() -> httpx.Response:
        async with create_safe_async_client(
            allow_hosts=(), allow_private=False, max_response_bytes=1024
        ) as client:
            return await client.get("http://ok.example.com/")

    resp = _run(go())
    assert resp.status_code == 200
    assert resp.content == b"small"
