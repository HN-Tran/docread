"""Google Cloud Vision REST-Adapter (DOCUMENT_TEXT_DETECTION)."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from .base import EngineResult

_GOOGLE_VISION_URL = "https://vision.googleapis.com/v1/images:annotate"


def _normalize_words_per_page(payload: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """Wörter aus ``fullTextAnnotation.pages[].blocks[].paragraphs[].words[]`` flach pro Seite.

    Google liefert Vertex-Koordinaten in Pixeln. Wir skalieren sie auf
    0–1000 anhand der Seitenmaße. Ein Wort = Konkatenation seiner Symbole.
    """
    responses = payload.get("responses") or []
    if not responses or not isinstance(responses, list):
        return []
    annotation = responses[0].get("fullTextAnnotation") if isinstance(responses[0], dict) else None
    if not isinstance(annotation, dict):
        return []
    pages = annotation.get("pages") or []
    if not isinstance(pages, list):
        return []

    out: list[list[dict[str, Any]]] = []
    for page in pages:
        if not isinstance(page, dict):
            out.append([])
            continue
        page_w = float(page.get("width") or 1000)
        page_h = float(page.get("height") or 1000)
        page_words: list[dict[str, Any]] = []
        for block in page.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            for paragraph in block.get("paragraphs") or []:
                if not isinstance(paragraph, dict):
                    continue
                for word in paragraph.get("words") or []:
                    if not isinstance(word, dict):
                        continue
                    text = "".join(
                        str(s.get("text") or "")
                        for s in (word.get("symbols") or [])
                        if isinstance(s, dict)
                    )
                    bbox = word.get("boundingBox") or {}
                    vertices = bbox.get("vertices") if isinstance(bbox, dict) else None
                    polygon: list[float] = []
                    if isinstance(vertices, list) and len(vertices) >= 4:
                        for v in vertices[:4]:
                            if not isinstance(v, dict):
                                polygon = []
                                break
                            x = float(v.get("x", 0)) / page_w * 1000
                            y = float(v.get("y", 0)) / page_h * 1000
                            polygon.extend([x, y])
                        if len(polygon) != 8:
                            polygon = []
                    page_words.append(
                        {
                            "content": text,
                            "polygon": polygon,
                            "confidence": float(word.get("confidence", 0.0)),
                        }
                    )
        out.append(page_words)
    return out


class GoogleVisionEngine:
    name = "google_vision"
    label = "Google Cloud Vision"

    def __init__(
        self,
        *,
        api_key: str,
        verify_ssl: bool = True,
        timeout_s: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError("Google-Vision-API-Key fehlt.")
        self._api_key = api_key
        self._verify_ssl = verify_ssl
        self._timeout_s = timeout_s

    async def analyze(self, image_bytes: bytes, content_type: str) -> EngineResult:
        del content_type  # Google nimmt base64 unabhängig vom Originaltyp.
        body = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                }
            ]
        }
        params = {"key": self._api_key}
        async with httpx.AsyncClient(timeout=self._timeout_s, verify=self._verify_ssl) as client:
            resp = await client.post(_GOOGLE_VISION_URL, json=body, params=params)
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()

        responses = payload.get("responses") or []
        annotation = (
            responses[0].get("fullTextAnnotation")
            if responses and isinstance(responses[0], dict)
            else None
        )
        text = str(annotation.get("text") if isinstance(annotation, dict) else "") or ""
        return EngineResult(
            text=text,
            words_per_page=_normalize_words_per_page(payload),
            raw=payload,
        )
