from __future__ import annotations

import base64
import importlib
import mimetypes
import time
from importlib.util import find_spec
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.services.ocr_pipeline import (
    PLAIN_TASK_OCR_TEXT,
    OCRPipeline,
    OCRResult,
    normalize_ocr_text_output,
)
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
_LAYOUT_VISUALIZATION_KEYS = (
    "_layout_visualization",
    "layout_visualization",
    "layout_visualizations",
    "layout_visualization_paths",
)


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

    @staticmethod
    def _load_glmocr_class() -> type[Any]:
        if find_spec("glmocr") is None:
            raise OllamaError(
                "Expert-Backend erfordert das Paket 'glmocr'. Bitte Abhängigkeit installieren."
            )

        try:
            module = importlib.import_module("glmocr")
            parser_class = module.GlmOcr
        except Exception as exc:  # noqa: BLE001
            raise OllamaError(
                f"Expert-Backend konnte 'glmocr.GlmOcr' nicht laden: {type(exc).__name__}: {exc}"
            ) from exc

        return parser_class

    def _build_parser(self, *, model: str, enable_layout: bool) -> Any:
        parser_class = self._load_glmocr_class()

        try:
            return parser_class(
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
        markdown = GLMOCRExpertPipeline._get_result_value(parse_result, "markdown_result", "")
        if isinstance(markdown, str):
            return normalize_ocr_text_output(markdown)
        if markdown is None:
            return ""
        return normalize_ocr_text_output(str(markdown))

    @staticmethod
    def _get_result_value(parse_result: Any, key: str, default: Any = None) -> Any:
        if isinstance(parse_result, dict):
            return parse_result.get(key, default)
        return getattr(parse_result, key, default)

    @staticmethod
    def _extract_error_message(parse_result: Any) -> str | None:
        error_message = GLMOCRExpertPipeline._get_result_value(parse_result, "_error")
        if error_message:
            return str(error_message).strip()
        return None

    @staticmethod
    def _normalize_layout_region(region: Any) -> dict[str, object] | None:
        if not isinstance(region, dict):
            return None

        normalized_region: dict[str, object] = {}

        index = region.get("index")
        if index is not None:
            try:
                normalized_region["index"] = int(index)
            except (TypeError, ValueError):
                normalized_region["index"] = str(index)

        label = region.get("label")
        if label is not None and str(label).strip():
            normalized_region["label"] = str(label).strip()

        content = region.get("content")
        if content is not None and str(content).strip():
            normalized_region["content"] = str(content).strip()

        bbox = region.get("bbox_2d")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                normalized_region["bbox_2d"] = [float(value) for value in bbox]
            except (TypeError, ValueError):
                pass

        if not normalized_region:
            return None
        return normalized_region

    @classmethod
    def _extract_layout(cls, parse_result: Any) -> list[dict[str, object]] | None:
        raw_layout = cls._get_result_value(parse_result, "json_result")
        if raw_layout is None:
            return None

        if isinstance(raw_layout, dict):
            candidate_pages = raw_layout.get("pages") or raw_layout.get("layout")
        else:
            candidate_pages = raw_layout

        if not isinstance(candidate_pages, list):
            return None

        pages: list[dict[str, object]] = []
        for page_index, page in enumerate(candidate_pages, start=1):
            raw_regions: Any
            page_number = page_index
            if isinstance(page, dict):
                raw_regions = page.get("regions")
                raw_page_number = page.get("page_number") or page.get("page") or page_index
                try:
                    page_number = int(raw_page_number)
                except (TypeError, ValueError):
                    page_number = page_index
            else:
                raw_regions = page

            if not isinstance(raw_regions, list):
                continue

            regions = [
                normalized_region
                for region in raw_regions
                if (normalized_region := cls._normalize_layout_region(region)) is not None
            ]
            pages.append({"page_number": page_number, "regions": regions})

        return pages or None

    @staticmethod
    def _path_to_data_url(path: Path) -> str | None:
        if not path.is_file():
            return None

        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not mime_type.startswith("image/"):
            return None

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @classmethod
    def _normalize_layout_visualization_value(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, dict):
            urls: list[str] = []
            for key in ("path", "paths", "url", "urls", "src", "image"):
                urls.extend(cls._normalize_layout_visualization_value(value.get(key)))
            return urls

        if isinstance(value, (list, tuple, set)):
            urls: list[str] = []
            for item in value:
                urls.extend(cls._normalize_layout_visualization_value(item))
            return urls

        if isinstance(value, (bytes, bytearray)):
            encoded = base64.b64encode(bytes(value)).decode("ascii")
            return [f"data:image/png;base64,{encoded}"]

        if isinstance(value, Path):
            data_url = cls._path_to_data_url(value)
            return [data_url] if data_url else []

        if isinstance(value, str):
            stripped_value = value.strip()
            if not stripped_value:
                return []
            if stripped_value.startswith(("data:image/", "http://", "https://")):
                return [stripped_value]

            data_url = cls._path_to_data_url(Path(stripped_value))
            return [data_url] if data_url else []

        return []

    @classmethod
    def _extract_layout_visualizations(cls, parse_result: Any) -> list[str] | None:
        visualizations: list[str] = []
        seen: set[str] = set()

        for key in _LAYOUT_VISUALIZATION_KEYS:
            for item in cls._normalize_layout_visualization_value(
                cls._get_result_value(parse_result, key)
            ):
                if item not in seen:
                    seen.add(item)
                    visualizations.append(item)

        raw_mapping = (
            parse_result
            if isinstance(parse_result, dict)
            else getattr(parse_result, "__dict__", {})
        )
        if isinstance(raw_mapping, dict):
            for key, value in raw_mapping.items():
                lowered_key = str(key).lower()
                if "layout" not in lowered_key or "visual" not in lowered_key:
                    continue
                for item in cls._normalize_layout_visualization_value(value):
                    if item not in seen:
                        seen.add(item)
                        visualizations.append(item)

        return visualizations or None

    @staticmethod
    def _build_text_from_layout(layout: list[dict[str, object]] | None) -> str:
        if not layout:
            return ""

        page_texts: list[str] = []
        for page_index, page in enumerate(layout, start=1):
            regions = page.get("regions")
            if not isinstance(regions, list):
                continue

            region_texts = [
                str(region.get("content", "")).strip()
                for region in regions
                if isinstance(region, dict) and str(region.get("content", "")).strip()
            ]
            if not region_texts:
                continue

            page_text = "\n".join(region_texts)
            if len(layout) > 1:
                page_number = page.get("page_number") or page_index
                page_texts.append(f"--- Seite {page_number} ---\n{page_text}")
            else:
                page_texts.append(page_text)

        return "\n\n".join(page_texts).strip()

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
                save_layout_visualization=selected_enable_layout,
            )

            layout = self._extract_layout(parse_result)
            text = self._extract_markdown(parse_result)
            layout_visualizations = (
                self._extract_layout_visualizations(parse_result)
                if selected_enable_layout
                else None
            )
            warnings: list[str] = []
            if not text:
                text = self._build_text_from_layout(layout)
                if text:
                    warnings.append(
                        "Leere Markdown-Hülle entfernt; Text aus Layout-Regionen rekonstruiert."
                    )
            if not text:
                raise OllamaError("Expert-Backend hat keinen OCR-Text zurückgegeben")
            error_message = self._extract_error_message(parse_result)
            if error_message:
                warnings.append(f"Expert-Backend Hinweis: {error_message}")
            if token_limit is not None:
                warnings.append("token_limit wird vom Expert-Backend nicht verwendet.")
            if gif_max_frames is not None:
                warnings.append("gif_max_frames ist nur für GIF-Verarbeitung relevant.")
            if layout:
                region_count = sum(len(page.get("regions", [])) for page in layout)
                warnings.append(
                    f"Expert-Layout: {region_count} Regionen auf {len(layout)} Seite(n) erkannt."
                )
            elif selected_enable_layout:
                warnings.append(
                    "Expert-Layout war aktiviert, aber GLM-OCR hat keine Layout-Regionen geliefert."
                )
            if layout_visualizations:
                warnings.append(
                    f"Expert-Layout-Visualisierung: {len(layout_visualizations)} Ansicht(en) verfügbar."
                )
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
                layout=layout,
                layout_visualizations=layout_visualizations,
            )
        except OllamaError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OllamaError(f"Expert-Backend Anfrage fehlgeschlagen: {exc}") from exc
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)
