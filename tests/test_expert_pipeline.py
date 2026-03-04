from __future__ import annotations

import asyncio
from typing import Any, cast

from app.services.expert_pipeline import GLMOCRExpertPipeline
from app.services.ocr_pipeline import OCRPipeline, OCRResult


def _png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfe\xa7\xd6\xe9Q\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class _FakeDirectPipeline:
    def __init__(self) -> None:
        self.calls = 0

    async def run(
        self,
        *,
        image_bytes: bytes,
        content_type: str | None = None,
        mode: str,
        schema_name: str | None,
        model: str | None = None,
        task: str | None = None,
        custom_prompt: str | None = None,
        token_limit: int | None = None,
        gif_max_frames: int | None = None,
        expert_enable_layout: bool | None = None,
    ) -> OCRResult:
        self.calls += 1
        return OCRResult(
            text="direct-fallback",
            structured=None,
            model=model or "m",
            mode=mode,
            schema_name=schema_name,
            latency_ms=1,
            warnings=[],
        )


class _FakeParser:
    def __init__(self) -> None:
        self.calls = 0

    def parse(
        self,
        input_source: str,
        *,
        save_results: bool = False,
        save_layout_visualization: bool = False,
    ) -> Any:
        self.calls += 1
        return type(
            "ParseResult",
            (),
            {
                "markdown_result": "Expert OCR text",
                "_error": None,
            },
        )()


def test_expert_falls_back_for_non_ocr_text_task() -> None:
    direct = _FakeDirectPipeline()
    expert = GLMOCRExpertPipeline(
        direct_pipeline=cast(OCRPipeline, direct),
        default_model="glm-ocr:latest",
        mode="selfhosted",
        ocr_api_host="localhost",
        ocr_api_port=11434,
        timeout_s=60.0,
        enable_layout=True,
    )

    result = asyncio.run(
        expert.run(
            image_bytes=_png_bytes(),
            content_type="image/png",
            mode="plain",
            schema_name=None,
            task="describe_image",
        )
    )
    assert result.text == "direct-fallback"
    assert direct.calls == 1
    assert any("direkte Pipeline wurde verwendet" in warning for warning in result.warnings)


def test_expert_uses_glm_parser_for_plain_ocr_text() -> None:
    direct = _FakeDirectPipeline()
    parser = _FakeParser()
    expert = GLMOCRExpertPipeline(
        direct_pipeline=cast(OCRPipeline, direct),
        default_model="glm-ocr:latest",
        mode="selfhosted",
        ocr_api_host="localhost",
        ocr_api_port=11434,
        timeout_s=60.0,
        enable_layout=True,
    )
    expert._get_parser = lambda *, model, enable_layout: parser  # type: ignore[method-assign]

    result = asyncio.run(
        expert.run(
            image_bytes=_png_bytes(),
            content_type="image/png",
            mode="plain",
            schema_name=None,
        )
    )
    assert result.text == "Expert OCR text"
    assert parser.calls == 1
    assert direct.calls == 0


def test_expert_respects_layout_override() -> None:
    direct = _FakeDirectPipeline()
    parser = _FakeParser()
    expert = GLMOCRExpertPipeline(
        direct_pipeline=cast(OCRPipeline, direct),
        default_model="glm-ocr:latest",
        mode="selfhosted",
        ocr_api_host="localhost",
        ocr_api_port=11434,
        timeout_s=60.0,
        enable_layout=True,
    )
    selected_layout_values: list[bool] = []

    def _fake_get_parser(*, model: str, enable_layout: bool) -> _FakeParser:
        selected_layout_values.append(enable_layout)
        return parser

    expert._get_parser = _fake_get_parser  # type: ignore[method-assign]

    result = asyncio.run(
        expert.run(
            image_bytes=_png_bytes(),
            content_type="image/png",
            mode="plain",
            schema_name=None,
            expert_enable_layout=False,
        )
    )
    assert result.text == "Expert OCR text"
    assert selected_layout_values == [False]
