from __future__ import annotations

import asyncio
from io import BytesIO
from typing import cast

import pytest
from PIL import Image

from app.services.ocr_pipeline import OCRPipeline
from app.services.ollama_client import OllamaClient


def _png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfe\xa7\xd6\xe9Q\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class FakeOllamaClient:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.last_prompt = ""
        self.prompts: list[str] = []
        self.last_model = ""
        self.last_num_ctx: int | None = None
        self.last_image_bytes = b""
        self.responses = list(responses) if responses is not None else []

    async def run_ocr(
        self, *, image_bytes: bytes, prompt: str, model: str, num_ctx: int | None = None
    ) -> str:
        self.last_image_bytes = image_bytes
        self.last_prompt = prompt
        self.prompts.append(prompt)
        self.last_model = model
        self.last_num_ctx = num_ctx
        if self.responses:
            return self.responses.pop(0)
        return "ok"


def _pdf_bytes() -> bytes:
    image = Image.new("RGB", (12, 12), color=(255, 255, 255))
    output = BytesIO()
    image.save(output, format="PDF")
    return output.getvalue()


def _pipeline(fake_client: FakeOllamaClient) -> OCRPipeline:
    return OCRPipeline(
        ollama_client=cast(OllamaClient, fake_client),
        default_model="glm-ocr:latest",
        default_token_limit=4096,
        max_image_dim=2048,
    )


def test_plain_describe_image_task_uses_describe_prompt() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    asyncio.run(
        pipeline.run(
            image_bytes=_png_bytes(),
            mode="plain",
            schema_name=None,
            task="describe_image",
            custom_prompt=None,
        )
    )
    assert "Beschreibe dieses Bild" in fake_client.last_prompt


def test_plain_custom_prompt_overrides_task_prompt() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    asyncio.run(
        pipeline.run(
            image_bytes=_png_bytes(),
            mode="plain",
            schema_name=None,
            task="describe_image",
            custom_prompt="Beschreibe dieses Bild in einem Satz.",
        )
    )
    assert fake_client.last_prompt == "Beschreibe dieses Bild in einem Satz."


def test_plain_unknown_task_raises() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            pipeline.run(
                image_bytes=_png_bytes(),
                mode="plain",
                schema_name=None,
                task="unknown_task",
                custom_prompt=None,
            )
        )
    assert "Unbekannte Aufgabe" in str(exc_info.value)


def test_plain_extract_table_markdown_task_uses_table_prompt() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    asyncio.run(
        pipeline.run(
            image_bytes=_png_bytes(),
            mode="plain",
            schema_name=None,
            task="extract_table_markdown",
            custom_prompt=None,
        )
    )
    assert "Markdown" in fake_client.last_prompt
    assert "Keine Tabelle erkannt." in fake_client.last_prompt


def test_plain_summarize_document_task_uses_summary_prompt() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    asyncio.run(
        pipeline.run(
            image_bytes=_png_bytes(),
            mode="plain",
            schema_name=None,
            task="summarize_document",
            custom_prompt=None,
        )
    )
    assert "Zusammenfassung" in fake_client.last_prompt
    assert "Stichpunkte" in fake_client.last_prompt


def test_structured_rejects_custom_prompt() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            pipeline.run(
                image_bytes=_png_bytes(),
                mode="structured",
                schema_name="invoice_basic",
                task=None,
                custom_prompt="Return JSON",
            )
        )
    assert "custom_prompt wird nur im Klartextmodus unterstützt" in str(exc_info.value)


def test_structured_auto_schema_detects_table_basic() -> None:
    fake_client = FakeOllamaClient(
        responses=[
            "table_basic",
            (
                '{"title":"Preisliste","columns":["Artikel","Preis"],'
                '"rows":[["A","10.00"]],"notes":null}'
            ),
        ]
    )
    pipeline = _pipeline(fake_client)
    result = asyncio.run(
        pipeline.run(
            image_bytes=_png_bytes(),
            mode="structured",
            schema_name="auto",
        )
    )
    assert result.schema_name == "table_basic"
    assert result.structured is not None
    assert result.structured["title"] == "Preisliste"
    assert any("Automatisch erkanntes Schema: table_basic" in w for w in result.warnings)
    assert "Verfügbare schema_name" in fake_client.prompts[0]


def test_structured_auto_schema_unknown_raises() -> None:
    fake_client = FakeOllamaClient(responses=["something_else"])
    pipeline = _pipeline(fake_client)
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            pipeline.run(
                image_bytes=_png_bytes(),
                mode="structured",
                schema_name=None,
            )
        )
    assert "Schema konnte nicht automatisch erkannt werden" in str(exc_info.value)


def test_default_token_limit_is_forwarded() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    asyncio.run(
        pipeline.run(
            image_bytes=_png_bytes(),
            mode="plain",
            schema_name=None,
            token_limit=None,
        )
    )
    assert fake_client.last_num_ctx == 4096


def test_token_limit_override_is_forwarded() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    asyncio.run(
        pipeline.run(
            image_bytes=_png_bytes(),
            mode="plain",
            schema_name=None,
            token_limit=8192,
        )
    )
    assert fake_client.last_num_ctx == 8192


def test_token_limit_must_be_positive() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            pipeline.run(
                image_bytes=_png_bytes(),
                mode="plain",
                schema_name=None,
                token_limit=0,
            )
        )
    assert "token_limit muss eine positive ganze Zahl sein" in str(exc_info.value)


def test_token_limit_must_not_exceed_max() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            pipeline.run(
                image_bytes=_png_bytes(),
                mode="plain",
                schema_name=None,
                token_limit=128001,
            )
        )
    assert "token_limit darf 128000 nicht überschreiten" in str(exc_info.value)


def test_pdf_input_is_rendered_to_png_before_ollama_call() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    asyncio.run(
        pipeline.run(
            image_bytes=_pdf_bytes(),
            content_type="application/pdf",
            mode="plain",
            schema_name=None,
        )
    )
    assert fake_client.last_image_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_invalid_pdf_raises_validation_error() -> None:
    fake_client = FakeOllamaClient()
    pipeline = _pipeline(fake_client)
    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            pipeline.run(
                image_bytes=b"not-a-pdf",
                content_type="application/pdf",
                mode="plain",
                schema_name=None,
            )
        )
    assert "PDF konnte nicht verarbeitet werden" in str(exc_info.value)
