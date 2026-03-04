from __future__ import annotations

import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.services.ocr_pipeline import PLAIN_TASK_OCR_TEXT, OCRPipeline, OCRResult
from app.services.ollama_client import OllamaError

_CONTENT_TYPE_SUFFIX_MAP = {
    "application/pdf": ".pdf",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tif": ".tif",
    "image/tiff": ".tif",
    "image/webp": ".webp",
    "image/x-tiff": ".tif",
}


class GLMOCRExpertPipeline:
    def __init__(
        self,
        *,
        direct_pipeline: OCRPipeline,
        default_model: str,
        mode: str,
        ocr_api_host: str,
        ocr_api_port: int,
        timeout_s: float,
        enable_layout: bool,
    ) -> None:
        self.direct_pipeline = direct_pipeline
        self.default_model = default_model
        self.mode = mode
        self.ocr_api_host = ocr_api_host
        self.ocr_api_port = ocr_api_port
        self.timeout_s = timeout_s
        self.enable_layout = enable_layout
        self._parser_cache: dict[tuple[str, bool], Any] = {}

    def _build_parser(self, *, model: str, enable_layout: bool) -> Any:
        try:
            from glmocr import GlmOcr
        except ImportError as exc:
            raise OllamaError(
                "Expert-Backend erfordert das Paket 'glmocr'. Bitte Abhängigkeit installieren."
            ) from exc

        try:
            return GlmOcr(
                mode=self.mode,
                model=model,
                ocr_api_host=self.ocr_api_host,
                ocr_api_port=self.ocr_api_port,
                timeout=max(1, int(self.timeout_s)),
                enable_layout=enable_layout,
            )
        except Exception as exc:  # noqa: BLE001
            raise OllamaError(f"Expert-Backend konnte nicht initialisiert werden: {exc}") from exc

    def _get_parser(self, *, model: str, enable_layout: bool) -> Any:
        cache_key = (model, enable_layout)
        parser = self._parser_cache.get(cache_key)
        if parser is None:
            parser = self._build_parser(model=model, enable_layout=enable_layout)
            self._parser_cache[cache_key] = parser
        return parser

    @staticmethod
    def _extract_markdown(parse_result: Any) -> str:
        if isinstance(parse_result, dict):
            markdown = parse_result.get("markdown_result", "")
            return str(markdown).strip() if markdown is not None else ""

        markdown = getattr(parse_result, "markdown_result", "")
        if isinstance(markdown, str):
            return markdown.strip()
        if markdown is None:
            return ""
        return str(markdown).strip()

    @staticmethod
    def _extract_error_message(parse_result: Any) -> str | None:
        if isinstance(parse_result, dict):
            error_message = parse_result.get("_error")
            return str(error_message).strip() if error_message else None
        error_message = getattr(parse_result, "_error", None)
        if error_message:
            return str(error_message).strip()
        return None

    async def _fallback_to_direct(
        self,
        *,
        reason: str,
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
    ) -> OCRResult:
        result = await self.direct_pipeline.run(
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
        )
        result.warnings.append(reason)
        return result

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
        selected_task = (task or PLAIN_TASK_OCR_TEXT).strip()
        selected_model = (model or "").strip() or self.default_model
        selected_enable_layout = (
            self.enable_layout if expert_enable_layout is None else expert_enable_layout
        )

        if mode != "plain":
            return await self._fallback_to_direct(
                reason="Expert-Backend unterstützt derzeit nur mode=plain; direkte Pipeline wurde verwendet.",
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
            )

        if selected_task != PLAIN_TASK_OCR_TEXT or (custom_prompt and custom_prompt.strip()):
            return await self._fallback_to_direct(
                reason=(
                    "Expert-Backend unterstützt derzeit nur ocr_text ohne custom_prompt; "
                    "direkte Pipeline wurde verwendet."
                ),
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
            )

        if content_type == "image/gif":
            return await self._fallback_to_direct(
                reason=(
                    "Animierte GIF-Verarbeitung bleibt in der direkten Pipeline, "
                    "um Storyboard/GIF-Frame-Steuerung zu nutzen."
                ),
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
            )

        suffix = _CONTENT_TYPE_SUFFIX_MAP.get(content_type or "", ".bin")
        temp_path: Path | None = None
        start = time.perf_counter()
        try:
            with NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as temp_file:
                temp_file.write(image_bytes)
                temp_path = Path(temp_file.name)

            parser = self._get_parser(model=selected_model, enable_layout=selected_enable_layout)
            parse_result = parser.parse(
                str(temp_path),
                save_results=False,
                save_layout_visualization=False,
            )

            text = self._extract_markdown(parse_result)
            if not text:
                raise OllamaError("Expert-Backend hat keinen OCR-Text zurückgegeben")

            warnings: list[str] = []
            error_message = self._extract_error_message(parse_result)
            if error_message:
                warnings.append(f"Expert-Backend Hinweis: {error_message}")
            if token_limit is not None:
                warnings.append("token_limit wird vom Expert-Backend nicht verwendet.")
            if gif_max_frames is not None:
                warnings.append("gif_max_frames ist nur für GIF-Verarbeitung relevant.")
            warnings.append(
                f"Expert-Backend wurde mit enable_layout={str(selected_enable_layout).lower()} ausgeführt."
            )

            latency_ms = int((time.perf_counter() - start) * 1000)
            return OCRResult(
                text=text,
                structured=None,
                model=selected_model,
                mode=mode,
                schema_name=None,
                latency_ms=latency_ms,
                warnings=warnings,
            )
        except OllamaError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OllamaError(f"Expert-Backend Anfrage fehlgeschlagen: {exc}") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
