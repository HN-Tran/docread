from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.routes import (
    _build_analyze_result,
    _scale_polygon_to_page_pixels,
    compat_analyze,
    compat_authentication_renew,
    compat_get_analyze_result,
    compat_service_ready,
    compat_sync_analyze,
    compat_usage_logs,
)
from app.config import get_settings
from app.services.analyze_operation_store import AnalyzeOperationStore
from app.services.backend_router import OCRBackendRouter
from app.services.page_number import footer_band_words


def _json_body(response: Any) -> Any:
    body = response.body
    raw = body.tobytes() if isinstance(body, memoryview) else body
    return json.loads(raw.decode("utf-8"))


def _png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfe\xa7\xd6\xe9Q\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class FakeCompatRequest:
    def __init__(
        self,
        *,
        body: bytes = b"",
        content_type: str | None = None,
        query_params: dict[str, str] | None = None,
    ) -> None:
        logger = logging.getLogger("test")
        self.app = SimpleNamespace(state=SimpleNamespace(logger=logger))
        self.headers = {} if content_type is None else {"content-type": content_type}
        self.query_params = query_params or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body

    def url_for(self, name: str, /, **path_params: str) -> str:
        if name != "compat_get_analyze_result":
            raise AssertionError(f"Unerwarteter Routenname: {name}")
        return (
            "http://testserver/formrecognizer/documentModels/"
            f"{path_params['modelId']}/analyzeResults/{path_params['rId']}"
        )


def _request(
    *,
    body: bytes = b"",
    content_type: str | None = None,
    query_params: dict[str, str] | None = None,
) -> Request:
    return cast(
        Request,
        FakeCompatRequest(body=body, content_type=content_type, query_params=query_params),
    )


class FakeBackendRouter:
    def __init__(self) -> None:
        self.last_call: dict[str, Any] = {}

    async def run(
        self,
        *,
        backend: str | None,
        image_bytes: bytes,
        content_type: str | None,
        mode: str,
        schema_name: str | None,
        model: str | None,
        task: str | None,
        custom_prompt: str | None,
        token_limit: int | None,
        gif_max_frames: int | None,
        expert_enable_layout: bool | None,
        expert_layout_model: str | None = None,
        expert_layout_threshold: float | None = None,
        expert_table_transformer: bool | None = None,
        expert_word_detector: str | None = None,
        inference_provider: str | None = None,
        **kwargs: object,
    ) -> Any:
        self.last_call = {
            "backend": backend,
            "image_bytes": image_bytes,
            "content_type": content_type,
            "mode": mode,
            "schema_name": schema_name,
            "model": model,
            "task": task,
            "custom_prompt": custom_prompt,
            "token_limit": token_limit,
            "gif_max_frames": gif_max_frames,
            "expert_enable_layout": expert_enable_layout,
            "expert_layout_model": expert_layout_model,
            "expert_table_transformer": expert_table_transformer,
            "expert_word_detector": expert_word_detector,
            "inference_provider": inference_provider,
        }
        result = type(
            "OCRResult",
            (),
            {
                "text": "page one\n\npage two",
                "layout": [
                    {
                        "page_number": 1,
                        "regions": [
                            {
                                "index": 0,
                                "label": "text_block",
                                "content": "page one",
                                "bbox_2d": [10.0, 10.0, 50.0, 50.0],
                                "polygon": [10.0, 10.0, 48.0, 12.0, 50.0, 50.0, 12.0, 48.0],
                                "confidence": 0.93,
                            }
                        ],
                    },
                    {
                        "page_number": 2,
                        "regions": [
                            {
                                "index": 0,
                                "label": "text_block",
                                "content": "page two",
                                "bbox_2d": [10.0, 10.0, 50.0, 50.0],
                                "polygon": [10.0, 10.0, 48.0, 12.0, 50.0, 50.0, 12.0, 48.0],
                                "confidence": 0.87,
                            }
                        ],
                    },
                ],
                "page_infos": [
                    {
                        "page_number": 1,
                        "angle": 0.0,
                        "width": 1000,
                        "height": 1200,
                        "unit": "pixel",
                        "words": [],
                        "lines": [],
                        "spans": [],
                        "kind": "document",
                    },
                    {
                        "page_number": 2,
                        "angle": 0.0,
                        "width": 1000,
                        "height": 1200,
                        "unit": "pixel",
                        "words": [],
                        "lines": [],
                        "spans": [],
                        "kind": "document",
                    },
                ],
                "page_texts": ["page one", "page two"],
            },
        )()
        return result, "direct"


class FakeBackendRouterWithoutLayout(FakeBackendRouter):
    async def run(
        self,
        *,
        backend: str | None,
        image_bytes: bytes,
        content_type: str | None,
        mode: str,
        schema_name: str | None,
        model: str | None,
        task: str | None,
        custom_prompt: str | None,
        token_limit: int | None,
        gif_max_frames: int | None,
        expert_enable_layout: bool | None,
        expert_layout_model: str | None = None,
        expert_layout_threshold: float | None = None,
        expert_table_transformer: bool | None = None,
        expert_word_detector: str | None = None,
        inference_provider: str | None = None,
        **kwargs: object,
    ) -> Any:
        result, selected_backend = await super().run(
            backend=backend,
            image_bytes=image_bytes,
            content_type=content_type,
            mode=mode,
            schema_name=schema_name,
            model=model,
            task=task,
            custom_prompt=custom_prompt,
            token_limit=token_limit,
            gif_max_frames=gif_max_frames,
            expert_enable_layout=expert_enable_layout,
            expert_layout_model=expert_layout_model,
            expert_table_transformer=expert_table_transformer,
            inference_provider=inference_provider,
            expert_word_detector=expert_word_detector,
        )
        result.layout = None
        return result, selected_backend


def _pipeline() -> OCRBackendRouter:
    return cast(OCRBackendRouter, FakeBackendRouter())


def test_scale_polygon_to_page_pixels_uses_page_resolution() -> None:
    polygon = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]
    scaled = _scale_polygon_to_page_pixels(polygon, page_width=2480, page_height=3508)
    assert scaled == pytest.approx(
        [
            248.0,
            701.6,
            744.0,
            1403.2,
            1240.0,
            2104.8,
            1736.0,
            2806.4,
        ]
    )


def test_compat_service_ready_payload() -> None:
    response = asyncio.run(compat_service_ready())
    payload = _json_body(response)
    assert payload["status"] == "ok"
    assert payload["service"] == "prebuilt-read"
    assert payload["apiStatus"] == "Healthy"
    assert response.headers["apim-request-id"]


def test_compat_usage_and_auth_stubs() -> None:
    usage_response = asyncio.run(compat_usage_logs(month="03", year="2026"))
    renew_response = asyncio.run(compat_authentication_renew(token="abc"))
    usage_payload = _json_body(usage_response)
    renew_payload = _json_body(renew_response)
    assert usage_payload["meters"] == []
    assert usage_payload["month"] == "03"
    assert renew_payload == {"status": "ok", "token": "abc"}
    assert usage_response.headers["apim-request-id"]
    assert renew_response.headers["apim-request-id"]


def test_sync_analyze_returns_azure_shape_and_filters_pages() -> None:
    fake_pipeline = FakeBackendRouter()
    response = asyncio.run(
        compat_sync_analyze(
            request=_request(body=_png_bytes(), content_type="application/octet-stream"),
            modelId="prebuilt-read",
            api_version="2022-08-31",
            pages="2",
            locale=None,
            string_index_type="unicodeCodePoint",
            backend="expert",
            expert_enable_layout=True,
            pipeline=cast(OCRBackendRouter, fake_pipeline),
        )
    )
    payload = _json_body(response)

    assert fake_pipeline.last_call["backend"] == "expert"
    assert fake_pipeline.last_call["expert_enable_layout"] is True
    assert fake_pipeline.last_call["mode"] == "plain"
    assert fake_pipeline.last_call["task"] == "ocr_text"
    assert response.headers["apim-request-id"]
    assert payload["status"] == "succeeded"
    assert payload["analyzeResult"]["apiVersion"] == "2022-08-31"
    assert payload["analyzeResult"]["modelId"] == "prebuilt-read"
    assert payload["analyzeResult"]["stringIndexType"] == "unicodeCodePoint"
    assert payload["analyzeResult"]["content"] == "page two"
    page = payload["analyzeResult"]["pages"][0]
    assert page["pageNumber"] == 2
    assert page["width"] == 1000
    assert page["height"] == 1200
    assert page["words"][0]["content"] == "page"
    assert page["words"][0]["polygon"] == pytest.approx(
        [10.0, 12.0, 29.0, 13.2, 31.0, 58.8, 12.0, 57.6]
    )
    assert page["words"][1]["polygon"] == pytest.approx(
        [33.75, 13.5, 48.0, 14.4, 50.0, 60.0, 35.75, 59.1]
    )
    assert page["lines"][0]["polygon"] == pytest.approx(
        [10.0, 12.0, 48.0, 14.4, 50.0, 60.0, 12.0, 57.6]
    )
    paragraph = payload["analyzeResult"]["paragraphs"][0]
    assert paragraph["content"] == "page two"
    assert paragraph["boundingRegions"][0]["pageNumber"] == 2
    assert paragraph["boundingRegions"][0]["polygon"] == pytest.approx(
        [10.0, 12.0, 48.0, 14.4, 50.0, 60.0, 12.0, 57.6]
    )


def test_sync_analyze_without_layout_keeps_word_shape_stable() -> None:
    fake_pipeline = FakeBackendRouterWithoutLayout()
    response = asyncio.run(
        compat_sync_analyze(
            request=_request(body=_png_bytes(), content_type="application/octet-stream"),
            modelId="prebuilt-read",
            api_version="2022-08-31",
            pages="1",
            locale=None,
            string_index_type="textElements",
            pipeline=cast(OCRBackendRouter, fake_pipeline),
        )
    )
    payload = _json_body(response)

    assert payload["analyzeResult"]["pages"] == [
        {
            "pageNumber": 1,
            "angle": 0.0,
            "width": 1000,
            "height": 1200,
            "unit": "pixel",
            "words": [
                {
                    "content": "page",
                    "span": {"offset": 0, "length": 4},
                    "confidence": 0.0,
                    "polygon": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                },
                {
                    "content": "one",
                    "span": {"offset": 5, "length": 3},
                    "confidence": 0.0,
                    "polygon": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                },
            ],
            "lines": [
                {
                    "content": "page one",
                    "spans": [{"offset": 0, "length": 8}],
                    "confidence": 0.0,
                    "polygon": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                }
            ],
            "spans": [{"offset": 0, "length": 8}],
            "kind": "document",
            "content": "page one",
        }
    ]
    assert payload["analyzeResult"]["paragraphs"] == [
        {
            "content": "page one",
            "spans": [{"offset": 0, "length": 8}],
            "boundingRegions": [],
        }
    ]


@pytest.mark.anyio
async def test_async_analyze_returns_operation_location_and_result_can_be_polled() -> None:
    fake_pipeline = FakeBackendRouter()
    store = AnalyzeOperationStore()
    analyze_response = await compat_analyze(
        request=_request(body=_png_bytes(), content_type="application/octet-stream"),
        modelId="prebuilt-read",
        api_version="2022-08-31",
        pages=None,
        locale=None,
        string_index_type=None,
        backend="expert",
        expert_enable_layout=True,
        pipeline=cast(OCRBackendRouter, fake_pipeline),
        store=store,
    )

    assert analyze_response.status_code == 202
    operation_location = analyze_response.headers["Operation-Location"]
    assert operation_location.endswith("?api-version=2022-08-31")
    assert analyze_response.headers["apim-request-id"]
    assert analyze_response.headers["Retry-After"] == "1"

    operation_id = operation_location.rsplit("/", 1)[-1].split("?", 1)[0]
    initial_poll = await compat_get_analyze_result(
        modelId="prebuilt-read",
        rId=operation_id,
        api_version="2022-08-31",
        store=store,
    )
    initial_payload = _json_body(initial_poll)
    assert initial_payload["status"] in {"notStarted", "running", "succeeded"}
    assert initial_poll.headers["apim-request-id"] == analyze_response.headers["apim-request-id"]

    await asyncio.sleep(0)
    assert fake_pipeline.last_call["backend"] == "expert"
    assert fake_pipeline.last_call["expert_enable_layout"] is True
    poll_response = await compat_get_analyze_result(
        modelId="prebuilt-read",
        rId=operation_id,
        api_version="2022-08-31",
        store=store,
    )
    payload = _json_body(poll_response)
    assert payload["status"] == "succeeded"
    assert payload["analyzeResult"]["modelId"] == "prebuilt-read"
    assert payload["analyzeResult"]["content"] == "page one\n\npage two"
    assert payload["analyzeResult"]["pages"][0]["spans"] == [{"offset": 0, "length": 8}]
    assert payload["analyzeResult"]["pages"][1]["spans"] == [{"offset": 10, "length": 8}]
    assert poll_response.headers["apim-request-id"] == analyze_response.headers["apim-request-id"]


def test_sync_analyze_rejects_unknown_model() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            compat_sync_analyze(
                request=_request(body=_png_bytes(), content_type="application/octet-stream"),
                modelId="unknown-model",
                api_version="2022-08-31",
                pages=None,
                locale=None,
                string_index_type=None,
                pipeline=_pipeline(),
            )
        )

    assert exc_info.value.status_code == 404


def test_sync_analyze_uses_configured_model_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_COMPAT_READ_MODEL", "prebuilt-layout")
    monkeypatch.setenv("AZURE_COMPAT_LAYOUT_MODEL", "prebuilt-layout")
    fake_pipeline = FakeBackendRouter()
    response = asyncio.run(
        compat_sync_analyze(
            request=_request(body=_png_bytes(), content_type="application/octet-stream"),
            modelId="prebuilt-layout",
            api_version="2022-08-31",
            pages=None,
            locale=None,
            string_index_type=None,
            expert_enable_layout=None,
            expert_per_region_ocr=None,
            expert_assemble_from_regions=None,
            pipeline=cast(OCRBackendRouter, fake_pipeline),
        )
    )
    payload = _json_body(response)

    assert fake_pipeline.last_call["expert_enable_layout"] is True
    assert payload["analyzeResult"]["modelId"] == "prebuilt-layout"


def test_compat_service_ready_uses_configured_read_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_COMPAT_READ_MODEL", "prebuilt-layout")
    monkeypatch.delenv("AZURE_COMPAT_LAYOUT_MODEL", raising=False)
    assert get_settings().azure_compat_read_model == "prebuilt-layout"
    response = asyncio.run(compat_service_ready())
    payload = _json_body(response)
    assert payload["service"] == "prebuilt-layout"


def _footer_word_polys() -> list[dict[str, object]]:
    return [
        {
            "content": "Seite",
            "confidence": 0.95,
            "polygon": [100.0, 910.0, 150.0, 910.0, 150.0, 930.0, 100.0, 930.0],
        },
        {
            "content": "1",
            "confidence": 0.95,
            "polygon": [160.0, 910.0, 180.0, 910.0, 180.0, 930.0, 160.0, 930.0],
        },
        {
            "content": "von",
            "confidence": 0.95,
            "polygon": [190.0, 910.0, 230.0, 910.0, 230.0, 930.0, 190.0, 930.0],
        },
        {
            "content": "5",
            "confidence": 0.95,
            "polygon": [240.0, 910.0, 260.0, 910.0, 260.0, 930.0, 240.0, 930.0],
        },
    ]


def test_build_analyze_result_layout_model_tags_page_number_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_COMPAT_LAYOUT_MODEL", "prebuilt-read")
    monkeypatch.setenv("AZURE_COMPAT_READ_MODEL", "prebuilt-layout")
    page_text = "Rechnung Nr. 4711\nSumme 10,00\nSeite 1 von 5"
    layout = [
        {
            "page_number": 1,
            "regions": [
                {
                    "index": 0,
                    "label": "text_block",
                    "content": "Rechnung Nr. 4711",
                    "bbox_2d": [50.0, 50.0, 900.0, 120.0],
                },
                {
                    "index": 1,
                    "label": "text_block",
                    "content": "Summe 10,00",
                    "bbox_2d": [50.0, 400.0, 900.0, 500.0],
                },
                {
                    "index": 2,
                    "label": "text_block",
                    "content": "Seite 1 von 5",
                    "bbox_2d": [50.0, 900.0, 900.0, 980.0],
                },
            ],
            "word_polys": _footer_word_polys(),
        }
    ]
    result = _build_analyze_result(
        content=page_text,
        model_id="prebuilt-read",
        layout=layout,
        page_infos=[
            {
                "page_number": 1,
                "width": 1000,
                "height": 1200,
                "unit": "pixel",
                "angle": 0.0,
            }
        ],
        page_texts=[page_text],
        azure_pixel_coordinates=True,
    )
    paragraphs = cast(list[object], result["paragraphs"])
    roles = [p.get("role") for p in paragraphs if isinstance(p, dict)]
    assert "pageNumber" in roles
    page_number_paragraphs = [
        p for p in paragraphs if isinstance(p, dict) and p.get("role") == "pageNumber"
    ]
    assert page_number_paragraphs[0]["content"] == "Seite 1 von 5"

    pages = cast(list[dict[str, object]], result["pages"])
    page = pages[0]
    words = cast(list[dict[str, object]], page["words"])
    assert words
    for word in words:
        polygon = word.get("polygon")
        assert isinstance(polygon, list)
        assert max(cast(list[float], polygon)[1::2]) > 0.0
    footer = footer_band_words(words, page_height=1200.0)
    footer_text = " ".join(str(w.get("content") or "") for w in footer)
    assert "Seite" in footer_text
    assert "5" in footer_text


def test_build_analyze_result_splits_glued_footer_counter_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_COMPAT_LAYOUT_MODEL", "prebuilt-read")
    monkeypatch.setenv("AZURE_COMPAT_READ_MODEL", "prebuilt-layout")
    raw_page_text = "Rechnung Nr. 4711\nSeite 2von2"
    layout = [
        {
            "page_number": 1,
            "regions": [
                {
                    "index": 0,
                    "label": "text_block",
                    "content": "Rechnung Nr. 4711",
                    "bbox_2d": [50.0, 50.0, 900.0, 120.0],
                },
                {
                    "index": 1,
                    "label": "text_block",
                    "content": "Seite 2von2",
                    "bbox_2d": [50.0, 900.0, 900.0, 980.0],
                },
            ],
            "word_polys": [
                {
                    "content": "Seite",
                    "confidence": 0.95,
                    "polygon": [100.0, 910.0, 150.0, 910.0, 150.0, 930.0, 100.0, 930.0],
                },
                {
                    "content": "2von2",
                    "confidence": 0.95,
                    "polygon": [160.0, 910.0, 280.0, 910.0, 280.0, 930.0, 160.0, 930.0],
                },
            ],
        }
    ]
    result = _build_analyze_result(
        content=raw_page_text,
        model_id="prebuilt-read",
        layout=layout,
        page_infos=[
            {
                "page_number": 1,
                "width": 1000,
                "height": 1200,
                "unit": "pixel",
                "angle": 0.0,
            }
        ],
        page_texts=[raw_page_text],
        azure_pixel_coordinates=True,
    )
    assert result["content"] == "Rechnung Nr. 4711\nSeite 2 von 2"
    pages = cast(list[dict[str, object]], result["pages"])
    words = cast(list[dict[str, object]], pages[0]["words"])
    footer = footer_band_words(words, page_height=1200.0)
    footer_contents = [str(w.get("content") or "") for w in footer]
    assert footer_contents == ["Seite", "2", "von", "2"]
    paragraphs = cast(list[dict[str, object]], result["paragraphs"])
    footer_paragraph = paragraphs[-1]
    assert footer_paragraph["content"] == "Seite 2 von 2"
    assert footer_paragraph.get("role") == "pageNumber"


def test_build_analyze_result_read_model_omits_paragraph_roles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AZURE_COMPAT_LAYOUT_MODEL", "prebuilt-read")
    monkeypatch.setenv("AZURE_COMPAT_READ_MODEL", "prebuilt-layout")
    page_text = "Seite 1 von 5"
    result = _build_analyze_result(
        content=page_text,
        model_id="prebuilt-layout",
        layout=None,
        page_infos=[{"page_number": 1, "width": 1000, "height": 1200, "unit": "pixel"}],
        page_texts=[page_text],
    )
    paragraphs = cast(list[object], result["paragraphs"])
    assert all("role" not in p for p in paragraphs if isinstance(p, dict))
