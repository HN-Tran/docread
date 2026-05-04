"""Generischer Textendpunkt: gibt nur Text zurück, keine Bounding Boxen.

Für interne / Custom-OCR-Services, die per HTTP entweder reinen Text oder
``{"text": "..."}`` liefern. Das Diff-Overlay bleibt leer (keine Polygone),
der Text-Diff funktioniert weiterhin.
"""

from __future__ import annotations

from typing import Any

import httpx

from .base import EngineResult


class PlainTextEngine:
    name = "plain_text"
    label = "Plain-Text-Endpunkt"

    def __init__(
        self,
        *,
        url: str,
        method: str = "POST",
        text_field: str = "text",
        auth_header_name: str | None = None,
        auth_header_value: str | None = None,
        verify_ssl: bool = True,
        timeout_s: float = 120.0,
    ) -> None:
        if not url:
            raise ValueError("Endpunkt-URL fehlt.")
        self._url = url
        self._method = method.upper()
        self._text_field = text_field or "text"
        self._auth_header_name = (auth_header_name or "").strip()
        self._auth_header_value = (auth_header_value or "").strip()
        self._verify_ssl = verify_ssl
        self._timeout_s = timeout_s

    async def analyze(self, image_bytes: bytes, content_type: str) -> EngineResult:
        headers: dict[str, str] = {
            "Content-Type": content_type or "application/octet-stream",
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.5",
        }
        if self._auth_header_name and self._auth_header_value:
            headers[self._auth_header_name] = self._auth_header_value

        async with httpx.AsyncClient(timeout=self._timeout_s, verify=self._verify_ssl) as client:
            resp = await client.request(
                self._method, self._url, content=image_bytes, headers=headers
            )
            resp.raise_for_status()
            ct = (resp.headers.get("content-type") or "").lower()
            text = ""
            payload: dict[str, Any] | None = None
            if "json" in ct:
                payload = resp.json()
                if isinstance(payload, dict):
                    candidate = payload.get(self._text_field)
                    text = str(candidate) if candidate is not None else ""
                elif isinstance(payload, str):
                    text = payload
            else:
                text = resp.text

        return EngineResult(text=text, words_per_page=[], raw=payload)
