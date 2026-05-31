"""End-to-end wiring tests: the real attack surfaces route through the guard.

These complement ``tests/test_safe_http.py`` (which unit-tests the guard in
isolation) by proving that the engines and routes the security report named
actually reject internal targets. The targets are IP literals, so resolution
is local and no real network connection is made -- the guard rejects them
before any socket connect.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar, cast

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.routes import _resolve_compat_request_input, peer_models
from app.services.compare_engines.azure import AzureEngine
from app.services.compare_engines.plain_text import PlainTextEngine
from app.services.compare_engines.self_peer import SelfPeerEngine
from app.services.safe_http import SSRFError

T = TypeVar("T")


def _run(coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _default_outbound_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure the secure defaults regardless of the dev environment.
    monkeypatch.delenv("OUTBOUND_ALLOW_PRIVATE", raising=False)
    monkeypatch.delenv("OUTBOUND_ALLOW_HOSTS", raising=False)


def test_plain_text_engine_blocks_loopback() -> None:
    engine = PlainTextEngine(url="http://127.0.0.1:9/ocr")
    with pytest.raises(SSRFError):
        _run(engine.analyze(b"data", "image/png"))


def test_self_peer_engine_blocks_private() -> None:
    engine = SelfPeerEngine(base_url="http://10.0.0.1")
    with pytest.raises(SSRFError):
        _run(engine.analyze(b"data", "image/png"))


def test_azure_engine_blocks_metadata_ip() -> None:
    engine = AzureEngine(endpoint="http://169.254.169.254", key="")
    with pytest.raises(SSRFError):
        _run(engine.analyze(b"data", "image/png"))


def test_peer_models_route_blocks_loopback() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _run(peer_models(url="http://127.0.0.1:9999"))
    assert exc_info.value.status_code in (400, 502)


class _FakeJSONRequest:
    def __init__(self, body: bytes, content_type: str) -> None:
        self.headers = {"content-type": content_type}
        self._body = body

    async def body(self) -> bytes:
        return self._body


def test_urlsource_fetch_blocks_metadata_ip() -> None:
    request = cast(
        Request,
        _FakeJSONRequest(
            b'{"urlSource": "http://169.254.169.254/latest/meta-data/"}',
            "application/json",
        ),
    )
    with pytest.raises(HTTPException) as exc_info:
        _run(_resolve_compat_request_input(request))
    assert exc_info.value.status_code == 400
