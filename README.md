<p align="center">
  <a href="README.md">English</a> · <a href="README_DE.md">Deutsch</a>
</p>

<h1 align="center">docread</h1>

<p align="center">
  <a href="https://github.com/HN-Tran/docread/actions/workflows/ci.yml"><img src="https://github.com/HN-Tran/docread/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/HN-Tran/docread/releases"><img src="https://img.shields.io/github/v/release/HN-Tran/docread?label=release" alt="Release"></a>
  <a href="https://github.com/HN-Tran/docread/blob/master/LICENSE"><img src="https://img.shields.io/github/license/HN-Tran/docread" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="docker-compose.yml"><img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose"></a>
</p>

<p align="center"><strong>Self-hosted document OCR with vision language models</strong></p>

<p align="center">
  Turn images, scans, PDFs, and Office documents into text on infrastructure you control — with a browser UI,
  a production REST API, and drop-in compatibility with Azure Document Intelligence.
</p>

## Why docread?

Most OCR setups force a trade-off: send documents to a cloud API (per-page cost, data leaves your network), or stitch together open-source tools that struggle with crooked camera shots, table grids, and multi-page files. **docread is one self-hosted app** that reads images (PNG, JPEG, WEBP, GIF, TIFF), multi-page PDFs, Word documents and templates (DOC, DOCX, DOT, DOTX, DOCM, DOTM), and PowerPoint slides (PPT, PPTX), runs modern vision LLMs locally, straightens messy scans before OCR, and still speaks the APIs your existing tools already expect.

## At a glance

| Capability | What you get |
|------------|--------------|
| **Your stack, your data** | Ollama, vLLM, llama.cpp, or any OpenAI-compatible vision server — no vendor lock-in, no outbound document upload. |
| **Two modes, one install** | **Direct** (`backend=direct`) for fast full-page OCR; **Dev** (`backend=expert`) for layout regions, tables, word boxes, and per-region deskew on difficult scans. |
| **Real-world scan handling** | Automatic deskew and quarter-turn detection (Tesseract OSD + PSM 2 fine skew, paperless-style) — built for A4 margins, curved book photos, and small content islands on large pages. |
| **See what the model saw** | Interactive preview with layout overlays, word polygons, markdown output, and per-region tilt metadata. |
| **Prove accuracy in-house** | Side-by-side compare against Azure, Google Vision, or another docread instance; batch benchmark with CER/WER when you have reference text; optional MLflow tracking. |
| **Drop-in for Azure workflows** | `prebuilt-read` sync/async endpoints compatible with Azure Document Intelligence (formerly Form Recognizer). |
| **Data sovereignty & privacy** | Self-hosted by design — no mandatory cloud OCR, no telemetry to the project maintainers; suitable for on-premises, private cloud, and air-gapped deployments when you control inference and storage. |

## Features

### Direct mode — fast full-page OCR (`backend=direct`)

Point a vision model at the whole page and get text back in seconds. Ideal for clean PDFs, quick extraction, and structured JSON when you define a schema. Works with any model your inference backend exposes (GLM-OCR, Qwen-VL, etc.).

### Dev mode — layout-aware document understanding (`backend=expert`)

When pages are harder than a flat scan, Dev mode runs a full document pipeline:

- **Layout detection** — finds text blocks, titles, tables, and figures (PP-DocLayoutV3 by default).
- **Per-region OCR** — each crop is sent to the vision model separately for better accuracy on dense pages.
- **Smart deskew** — page-level cardinal orientation plus region-level fine skew for camera captures and table strips.
- **Table cells** — optional Microsoft Table Transformer for cell-level bounding boxes.
- **Word polygons** — DocTR or PaddleOCR word boxes overlaid on the preview.
- **Text anchoring** — fuzzy-match region OCR back to full-page text to reduce duplication artifacts.

### Evaluation & benchmarking

- **Compare** (`POST /api/compare`) — run docread against Azure, Google Vision, a peer instance, or any HTTP text endpoint; token-level diff and optional CER/WER against ground truth.
- **Benchmark** (`/benchmark` UI or `POST /api/benchmark`) — batch many files × many models/runners with aggregate metrics and CSV export.
- **Offline eval** (`eval/run`) — regression suite on a fixed sample set with a manifest of expected text.

### Integrations

- **REST API** with Swagger UI (`/docs`), ReDoc (`/redoc`), and OpenAPI JSON.
- **Web UI** at `/` — drag-and-drop upload, layout/word/markdown/diff views, EN/DE locale.
- **Azure Document Intelligence compatibility** — `prebuilt-read` sync and async analyze endpoints.
- **Docker Compose** — app container (CPU default; optional NVIDIA/AMD GPU for layout); stack file bundles docread + llama.cpp GLM-OCR. Host Ollama supported via default env.

## Privacy & data sovereignty

docread is built for organizations that cannot send citizen files, case documents, or internal records to third-party cloud OCR APIs — **municipalities, agencies, healthcare, legal, and regulated industries**.

| Concern | How docread helps |
|---------|-------------------|
| **Data residency (EU / GDPR)** | Processing stays on **your** infrastructure. You choose where the app and vision model run (EU datacenter, government private cloud, offline site). |
| **No vendor lock-in or telemetry** | The application does **not** send documents or usage data to the project maintainers. Outbound traffic is limited to what **you** configure: your inference server, optional compare engines, and (once) model downloads you control. |
| **Air-gapped / isolated networks** | Runnable offline after models and layout weights are cached. Inference via local Ollama or llama.cpp on the same network segment — no Internet required at OCR time. |
| **Replace cloud OCR gradually** | Azure Document Intelligence–compatible endpoints let existing integrations target an **on-premises** docread instance instead of a public cloud API. |
| **Operational control** | You govern retention: async analyze results (`ANALYZE_STORE_DIR`), benchmark job TTL, logs, TLS, and access via your reverse proxy and IAM. |
| **Transparency** | Apache 2.0, auditable source, standard Docker deployment on VMs or Kubernetes under your security baseline. |

**What we do not claim:** docread is **software**, not a certified compliance product. There is no “GDPR certificate” for an app. We do **not** state ISO 27001, SOC 2, BSI IT-Grundschutz, or sector approvals — those belong to **your** deployment, processes, and (where needed) a DPIA / legal review. Optional compare and benchmark features can call **third-party** APIs (Azure, Google); disable them or keep them in isolated non-production environments if policy requires.

**Typical public-sector setup:** docread plus a local vision model on government-managed hardware, no external OCR in production, compare mode only in a non-production test environment if needed.

## Requirements

- Python 3.12+
- `uv` 0.10+
- A vision-capable model on your inference backend (Ollama by default, or an OpenAI-compatible server)

## Setup

```bash
uv sync --all-groups
```

### Configuration

Copy [`.env.example`](.env.example) to `.env` for Docker Compose. Defaults below match `app/config.py` unless noted.

#### Inference (vision LLM)

| Variable | Default | Description |
|----------|---------|-------------|
| `INFERENCE_PROVIDER` | `ollama` | `ollama` or `openai_compatible` (vLLM, llama.cpp, …). Details: [`docs/inference-providers.md`](docs/inference-providers.md). |
| `INFERENCE_BASE_URL` | `http://localhost:11434` | API base URL. Falls back to `OLLAMA_BASE_URL`. |
| `INFERENCE_MODEL` | `glm-ocr:latest` | Default model when the request omits `model`. Falls back to `OLLAMA_MODEL`. |
| `INFERENCE_API_KEY` | *(empty)* | Optional Bearer token for OpenAI-compatible servers. |
| `INFERENCE_VISION_MODELS` | *(empty)* | Comma-separated allowlist for `GET /api/models?vision_only=true`. |
| `INFERENCE_VISION_PROBE` | `true` | Probe OpenAI-compatible `/models` when the allowlist is empty. |
| `INFERENCE_EXTRA_PROVIDERS` | *(empty)* | JSON map of extra provider configs. |
| `DEFAULT_TOKEN_LIMIT` | `16384` | Default Ollama `num_ctx` / context limit (`1..128000`). |
| `REQUEST_TIMEOUT_S` | `120` | HTTP timeout for inference calls (seconds). |
| `VERIFY_SSL` | `false` | TLS certificate verification for inference HTTP clients. |

Legacy aliases `OLLAMA_BASE_URL` and `OLLAMA_MODEL` still work. Per-request: form field `inference_provider`; model as `provider/model` (e.g. `openai_compatible/my-vlm`).

OpenAI-compatible example (GLM-OCR via Docker: [`docs/llamacpp-docker-glm-ocr.md`](docs/llamacpp-docker-glm-ocr.md)):

| Variable | Example |
|----------|---------|
| `INFERENCE_PROVIDER` | `openai_compatible` |
| `INFERENCE_BASE_URL` | `http://localhost:8080/v1` |
| `INFERENCE_MODEL` | `GLM-OCR-Q8_0.gguf` |

#### OCR backends

| Variable | Default | Description |
|----------|---------|-------------|
| `OCR_BACKEND` | `expert` | `direct` (full-page OCR) or `expert` (Dev: layout + region OCR). UI labels: **Direct** / **Dev**. |
| `OCR_EXPERT_ENABLE_LAYOUT` | `true` | Run layout detection in Dev mode. |
| `OCR_EXPERT_LAYOUT_MODEL` | `PaddlePaddle/PP-DocLayoutV3_safetensors` | Hugging Face layout model (`HFLayoutDetector`). |
| `OCR_EXPERT_LAYOUT_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, or `mps` for layout inference. |
| `OCR_EXPERT_LAYOUT_THRESHOLD` | *(per model)* | Optional global confidence threshold (`0..1`); overridable per request. |
| `OCR_EXPERT_LAYOUT_MAX_DIM` | `1800` | Long edge cap for layout detection (boxes mapped back to full resolution). |
| `OCR_EXPERT_TABLE_TRANSFORMER` | `false` | Microsoft Table Transformer cell boxes on table regions. |
| `OCR_EXPERT_PER_REGION_OCR` | `true` | OCR per layout region (off = layout only, faster). |
| `OCR_EXPERT_TEXT_ANCHOR` | `true` | Fuzzy-match region OCR back to full-page text. |
| `OCR_EXPERT_TEXT_ANCHOR_THRESHOLD` | `60` | RapidFuzz score threshold for text anchoring. |
| `OCR_EXPERT_COMPARE_INCLUDE_DETECTOR_ONLY` | `false` | Include detector-only words in compare diff. |
| `OCR_WORD_DETECTOR` | `doctr` | Word polygons: `none`, `paddleocr`, or `doctr`. |

#### Scan deskew

| Variable | Default | Description |
|----------|---------|-------------|
| `DESKEW_ENABLED` | `true` | Deskew each page before OCR/layout. |
| `DESKEW_PAGE_CARDINAL` | `true` | Quarter-turn detection on content-bbox probe (margin scans). |
| `DESKEW_OSD` | `1` | Tesseract OSD on probe (needs `pytesseract`; in Docker image). |
| `DESKEW_OSD_MIN_CONFIDENCE` | `1.0` | Minimum OSD confidence to apply a cardinal hint. |
| `DESKEW_TESSERACT_FINE` | `1` | Fine skew via Tesseract PSM 2 deskew (paperless-ngx / OCRmyPDF). |
| `DESKEW_TESSERACT_LANG` | `osd` | Tesseract `-l` for deskew (`osd`, `eng+deu`, etc.). |
| `DESKEW_TESSERACT_TIMEOUT` | `60` | Seconds before giving up on Tesseract deskew. |
| `DESKEW_FINE_SCAN_DIM` | `2400` | Max dimension for tiled fine-skew search. |
| `DESKEW_MIN_ANGLE_DEG` | `0.5` | Ignore skew corrections smaller than this (degrees). |
| `DESKEW_CONTENT_BBOX_MAX_FILL` | `0.72` | Use full-page probe when ink fill exceeds this fraction. |
| `DESKEW_QUARTER_TURN` | `auto` | Force `90`, `270`, `-90`, or `auto` cardinal override. |
| `DESKEW_DEBUG` | `0` | Log deskew decisions to server logs and OCR `warnings`. |

#### Upload limits & preprocessing

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_UPLOAD_BYTES` | `8388608` | Maximum upload size (8 MiB). |
| `MAX_IMAGE_DIM` | `3600` | Max long edge after load (pixels). |
| `OCR_BINARIZED_MIN_DIM` | `1800` | Upscale 1-bit / grayscale inputs to at least this size. |
| `ANALYZE_STORE_DIR` | `/tmp/docread-analyze-results` | Persisted Azure-compat analyze results. |

#### Compare presets (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_PRESET_LABEL` | *(empty)* | Label for one-click Azure compare button in the UI. |
| `AZURE_PRESET_ENDPOINT` | *(empty)* | Azure endpoint URL for that preset. |
| `AZURE_PRESET_LAYOUT_ENDPOINT` | *(empty)* | Optional second preset (layout model). |
| `AZURE_PRESET_KEY` | *(empty)* | Server-side key injected when the UI calls the preset URL without a key. |

#### Outbound requests & SSRF guard

Compare/peer/`urlSource` features fetch caller-supplied URLs server-side. By default only public addresses are allowed (internal/loopback targets are blocked). See [`docs/security.md`](docs/security.md) for the full model.

| Variable | Default | Description |
|----------|---------|-------------|
| `OUTBOUND_ALLOW_HOSTS` | *(empty)* | Comma-separated hostnames/CIDRs allowed as outbound targets even if internal (e.g. `localhost,172.17.0.0/16`). |
| `OUTBOUND_ALLOW_PRIVATE` | `false` | Allow any private/internal address. Trusted single-user/local deployments only. |
| `OUTBOUND_MAX_RESPONSE_BYTES` | `67108864` | Cap (bytes) on a server-fetched response body; `0` disables. |

#### Benchmark & MLflow

| Variable | Default | Description |
|----------|---------|-------------|
| `BENCHMARK_MAX_FILES` | `50` | Max files per benchmark job. |
| `BENCHMARK_MAX_RUNNERS` | `5` | Max runners (models + engines) per job. |
| `BENCHMARK_JOB_TTL_S` | `3600` | In-memory job retention (seconds). |
| `MLFLOW_TRACKING_URI` | *(empty)* | e.g. `http://mlflow:5000` or `file:./mlruns`; empty disables tracking. |
| `MLFLOW_EXPERIMENT_NAME` | `docread` | MLflow experiment name. |

#### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_LOCALE` | `en` | UI language: `en` or `de`. |
| `APP_BASE_PATH` | *(empty)* | URL prefix when mounted behind a reverse proxy. |
| `HOST` | `127.0.0.1` | Bind address for `uvicorn`. |
| `PORT` | `8000` | Bind port for `uvicorn`. |

### Input preprocessing and deskew

Shared steps (`app/services/ocr_pipeline.py`, `app/services/deskew.py`):

- RGBA/LA and transparent palette PNGs are composited onto a **white** background (avoids black defaults that would make black text on a transparent background invisible).
- Bitonal (`1`) and grayscale (`L`) inputs are upscaled to at least `OCR_BINARIZED_MIN_DIM` pixels (default 1800) so models can more reliably distinguish `l`/`I`/`1`.
- When `DESKEW_ENABLED=true` (default), each page is deskewed **before** OCR. Cardinal turns use a content-bbox probe (helpful on A4 scans with large margins) plus optional Tesseract OSD (`DESKEW_OSD=1`). Fine skew uses Tesseract PSM 2 deskew (`DESKEW_TESSERACT_FINE=1`), same as paperless-ngx / OCRmyPDF — not projection variance.
- PDF `/Rotate` metadata is baked into pixels before deskew when rendering pages.

**Dev backend** (`app/services/document_pipeline.py`):

- Page deskew runs first; layout detection sees the corrected preview image (downscaled to `OCR_EXPERT_LAYOUT_MAX_DIM`, default 1800, then boxes mapped back to full resolution for crops).
- Regions smaller than 40% of the page area may receive an extra region-level deskew on the crop before OCR.
- `page_infos[].angle` and Azure `pages[].angle` report the **net CCW correction applied** to that page (0 when none).
- Each layout region may include `angle` (tilt on the **original** scan), `preview_angle` (= original − page correction), and `deskew_correction_ccw` (extra CCW applied on the region crop).

Install optional OSD locally: `uv sync --extra osd` or `pip install '.[osd]'`.

## Start

```bash
uv run uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000`

## API

Interactive reference (authoritative for request fields and types): [`/docs`](http://127.0.0.1:8000/docs) (Swagger UI), [`/redoc`](http://127.0.0.1:8000/redoc), and [`/openapi.json`](http://127.0.0.1:8000/openapi.json). Structured schema names: `GET /api/schemas`.

`POST /api/ocr` accepts either `multipart/form-data` or a raw body with `Content-Type: application/octet-stream`.

In addition, docread exposes Azure Document Intelligence read-compatible REST endpoints:

- `GET /status`
- `GET /ready`
- `GET /ContainerReadiness`
- `GET /ContainerLiveness`
- `POST /formrecognizer/documentModels/prebuilt-read:syncAnalyze`
- `POST /formrecognizer/documentModels/prebuilt-read:analyze`
- `GET /formrecognizer/documentModels/prebuilt-read/analyzeResults/{resultId}`

Compatibility notes:

- `api-version=2022-08-31` is required.
- `application/octet-stream` and `application/json` with `{"urlSource":"..."}` are accepted.
- `:analyze` returns `202` plus `Operation-Location`; processing runs in the background and is stored in the analyze store for polling.
- Analyze results are additionally persisted on the filesystem under `ANALYZE_STORE_DIR` so polling continues to work after a process restart on the same volume.
- `pages` and `stringIndexType` are accepted; `pages` currently only filters the response payload, not the actual OCR execution.
- `modelId` is limited to `prebuilt-read`.
- `pages`, `paragraphs`, `lines`, `words`, and `spans` are now best-effort populated from OCR text and layout data. `textElements` remains a pragmatic approximation, not a complete grapheme cluster implementation.
- `pages[].angle` reports the net **CCW correction** applied to that page when deskew is enabled (aligned with native `page_infos[].angle`, not Azure’s clockwise field semantics).
- `pages[].words` uses — when `OCR_WORD_DETECTOR=doctr|paddleocr` is active and the detector provided word polygons — the real detector boxes (same data as the "Words" tab in the browser) instead of the synthetic word wrappers from layout regions. Without a detector the previous fallback remains.

#### `POST /api/ocr`

Required: upload bytes — multipart field `file`, or raw `application/octet-stream` body. When `mode=structured`, `schema_name` is required too. All other fields (`backend`, `model`, `task`, `expert_*`, …) are optional overrides; see OpenAPI for the full list.

Raw upload: pass the same optional parameters as query strings. Format detection uses the file signature (`png`, `jpeg`, `webp`, `gif`, `tiff`, `pdf`, `doc`, `docx`, `dot`, `dotx`, `ppt`, `pptx`, …); Office formats are converted to PDF via LibreOffice.

```powershell
Invoke-RestMethod -Method POST `
  -Uri 'https://HOST/api/ocr?backend=direct&mode=plain' `
  -ContentType 'application/octet-stream' `
  -InFile 'C:\path\scan.tiff'
```

**Behavior (not repeated in OpenAPI)**

- **Inputs:** PDFs → all pages; animated GIFs → sampled frames (default 8, cap via `gif_max_frames`). `describe_image` on GIFs uses one storyboard call.
- **Backends:** `direct` — vision LLM per page/frame, text in the **Text** tab. `expert` (Dev) — layout pipeline when `mode=plain` and `task=ocr_text`; otherwise falls back to Direct. Dev may add `markdown` (UI preview) while `text` stays raw.
- **Dev layout:** Hugging Face object detection via `OCR_EXPERT_LAYOUT_MODEL` / `expert_layout_model` (weights you configure; not shipped with docread). Axis-aligned `bbox_2d` regions; optional Table Transformer `cells` on table regions.

Example response:

```json
{
  "status": "succeeded",
  "createdDateTime": "2026-03-09T08:00:00+00:00",
  "lastUpdatedDateTime": "2026-03-09T08:00:01+00:00",
  "analyzeResult": {
    "apiVersion": "2026-03-09-preview",
    "modelId": "glm-ocr:latest",
    "stringIndexType": "textElements",
    "content": "...",
    "pages": [
      {
        "pageNumber": 1,
        "angle": 0.0,
        "width": 2480,
        "height": 3508,
        "unit": "pixel",
        "words": [],
        "lines": [],
        "spans": [],
        "kind": "document",
        "content": "..."
      }
    ],
    "paragraphs": [
      {
        "content": "...",
        "spans": []
      }
    ],
    "styles": [],
    "languages": []
  },
  "text": "...",
  "markdown": "# Title\n\n...",
  "structured": null,
  "layout": [
    {
      "page_number": 1,
      "page_deskew_correction_ccw": 90.0,
      "regions": [
        {
          "index": 0,
          "label": "text_block",
          "content": "...",
          "bbox_2d": [100.0, 120.0, 900.0, 260.0],
          "confidence": 0.96,
          "angle": 0.0,
          "preview_angle": 0.0,
          "deskew_correction_ccw": 0.0
        }
      ]
    }
  ],
  "model": "glm-ocr:latest",
  "backend": "direct",
  "mode": "plain",
  "schema_name": null,
  "latency_ms": 1234,
  "warnings": []
}
```

## Comparison with External OCR Engine

`POST /api/compare` runs our OCR pipeline in parallel with an external engine and returns a diff, side-by-side metrics, and (optionally) CER/WER against a reference text. `GET /api/compare/engines` lists the supported engines.

**Supported engines** (`engine` form field):

| `engine` | Configuration fields | Notes |
|---|---|---|
| `azure` | `azure_endpoint`, `azure_key` | Azure Form Recognizer / Document Intelligence prebuilt-read. Uses async polling. |
| `self_peer` | `peer_base_url`, `peer_backend` | Posts the file to `<peer_base_url>/api/ocr` of another instance of this app — useful for comparing two configurations or model versions directly. |
| `google_vision` | `google_api_key` | Google Cloud Vision REST (`DOCUMENT_TEXT_DETECTION`). |
| `plain_text` | `plain_text_url`, optional `plain_text_method`, `plain_text_field`, `plain_text_auth_header`, `plain_text_auth_value` | Generic endpoint that returns either plain text or `{"text": "..."}`. Provides no bounding boxes; diff remains text-based. |

**Optional parameters** (engine-independent):

- `reference_text`: Ground-truth text. When set, the response adds a `metrics.reference` block with true CER, WER, and token-F1 for both sides.
- `expert_*` and `backend`: apply to our own OCR side (see above).
- `expert_compare_include_detector_only`: additionally includes word polygons from the detector that did not hit a layout token in the diff.

**Metrics in response** (`metrics` block):

- `intrinsic`: tokens, characters, avg confidence, latency per page.
- `comparison`: pairwise Δ characters, Δ words (normalized Levenshtein distance — deliberately _not_ CER/WER since neither side is ground truth), token Jaccard, token precision/recall/F1.
- `reference`: only when `reference_text` was provided — true CER, WER, token-F1 per side.

**Azure preset** (browser workflow):
When `AZURE_PRESET_LABEL`, `AZURE_PRESET_ENDPOINT`, and `AZURE_PRESET_KEY` are set, the compare form shows a quick button with the label. If the browser sends a request to exactly this endpoint URL without an API key, the server adds the key internally — the secret never leaves the backend.

**Why no AWS Textract?**
AWS Textract is deliberately _not_ included because it requires SigV4 signing, which requires either `boto3` (~10 MB) or a custom signing implementation. Since there is no concrete AWS requirement, the dependency stays out. To add it:

1. Add `boto3` as an optional extra in `pyproject.toml` (analogous to the existing `paddle` extra).
2. Write `app/services/compare_engines/aws_textract.py` following the pattern of the other engines (class with `name`/`label`/`async def analyze`).
3. Register in `app/services/compare_engines/registry.py`.

## Batch Benchmark

`/benchmark` (UI) or `POST /api/benchmark` run N files against M runners — runners are either local Ollama models or external engines from the compare flow. Per row, token/character count, latency, and (if reference text was provided) CER/WER/token-F1 are calculated. The aggregate per runner delivers mean + standard deviation.

### How it works internally

Benchmark jobs live in a **process-local** `BenchmarkJobStore` (`app/services/benchmark.py`): an `asyncio.Lock` + in-memory `dict`. Not shared across replicas; lost on restart unless you exported CSV/MLflow first.

- **Worker:** `POST /api/benchmark` returns `{job_id}` immediately; `run_benchmark_job` runs as `asyncio.create_task` and updates `job.rows` in place.
- **Sequential execution:** (file × runner) pairs run one after another so Ollama latency stays comparable (no parallel local inference yet).
- **Progress:** poll `GET /api/benchmark/{job_id}` (UI ~2 s). Rows: `pending → running → done|error`. Optional `POST /api/benchmark/{job_id}/cancel` sets `cancelled`.
- **Retention:** after the job finishes (or is cancelled), it is dropped automatically after `BENCHMARK_JOB_TTL_S` (default 3600). `DELETE /api/benchmark/{job_id}` removes it immediately.
- **Exports:** `GET /api/benchmark/{job_id}/csv` for results; optional MLflow parent/child runs when `MLFLOW_TRACKING_URI` is set (see below).

Azure-compat `:analyze` jobs use a **separate** filesystem store (`ANALYZE_STORE_DIR`), not the benchmark dict.

### Job lifecycle

```
POST   /api/benchmark                    → { job_id }
GET    /api/benchmark                    → { jobs: [...] }
GET    /api/benchmark/{job_id}           → job state + progress
POST   /api/benchmark/{job_id}/cancel    → cancel running job
GET    /api/benchmark/{job_id}/csv       → CSV export
DELETE /api/benchmark/{job_id}           → drop job now
```

Hard caps configurable via `BENCHMARK_MAX_FILES` (default 50) and `BENCHMARK_MAX_RUNNERS` (default 5).

### Controllable via REST (curl example)

The browser UI is optional — the API is self-contained:

```bash
# 1. Submit job (two files, one reference text each, two models, plus Azure)
JOB=$(curl -s -X POST http://localhost:8000/api/benchmark \
  -F "files=@doc1.pdf" \
  -F "files=@doc2.pdf" \
  -F "references=Hello world from doc1" \
  -F "references=" \
  -F "models=glm-ocr:latest,qwen2.5vl:7b" \
  -F "engines=azure" \
  -F "azure_endpoint=https://your-host" \
  -F "azure_key=…" \
  | jq -r .job_id)

# 2. Poll until done
while true; do
  status=$(curl -s "http://localhost:8000/api/benchmark/$JOB" | jq -r .status)
  echo "$status"
  [[ "$status" == "done" || "$status" == "failed" ]] && break
  sleep 2
done

# 3. Fetch result as CSV
curl -s "http://localhost:8000/api/benchmark/$JOB/csv" -o "benchmark-$JOB.csv"

# 4. Remove from server memory (optional)
curl -s -X DELETE "http://localhost:8000/api/benchmark/$JOB"
```

`models` and `engines` are comma-separated lists. At least one must be non-empty. `references` must be provided in the same order as `files` — an empty string means no reference for that file.

Engine-specific fields (only the selected engines are served):

| Engine | Required fields |
|---|---|
| `azure` | `azure_endpoint`, `azure_key` |
| `self_peer` | `peer_base_url`, optional `peer_backend`, `peer_model` |
| `google_vision` | `google_api_key` |
| `plain_text` | `plain_text_url`, optional `plain_text_method`, `plain_text_field`, `plain_text_auth_header`, `plain_text_auth_value` |
| `local_models` | (not via engines — see `models`) |

### Response schema (`GET /api/benchmark/{job_id}`)

```json
{
  "id": "abc123…",
  "created_at": "2026-05-…",
  "status": "running",
  "progress": {"done": 5, "total": 10},
  "options": {"files": [...], "models": [...], "engines": [...]},
  "rows": [
    {
      "file_index": 0,
      "file_name": "doc1.pdf",
      "runner_kind": "local_model",
      "runner_label": "glm-ocr:latest",
      "status": "done",
      "text_chars": 1234,
      "text_tokens": 192,
      "latency_ms": 4521,
      "cer": 0.082,
      "wer": 0.137,
      "token_f1": 0.882,
      "avg_confidence": 0.94,
      "warnings": [],
      "error": null
    }
  ],
  "aggregate": {
    "per_runner": {
      "glm-ocr:latest": {
        "doc_count": 2, "success_count": 2, "failure_count": 0,
        "mean_cer": 0.082, "stdev_cer": 0.041,
        "mean_wer": 0.137, "mean_token_f1": 0.882,
        "mean_latency_ms": 4231
      }
    }
  },
  "error": null,
  "mlflow": {"run_id": "…", "run_url": "https://mlflow…/#/experiments/…/runs/…"}
}
```

### MLflow Tracking (optional)

When `MLFLOW_TRACKING_URI` is set AND `mlflow` is installed (`pip install '.[mlflow]'`), the worker additionally writes:

- a parent run per job with aggregate metrics (`<runner>.mean_cer`, …),
- per (file, runner) a nested child run with parameters, metrics, and `hypothesis.txt` / `reference.txt` as artifacts.

Configuration:

```bash
export MLFLOW_TRACKING_URI=http://mlflow:5000   # or file:./mlruns
export MLFLOW_EXPERIMENT_NAME=docread          # default: "docread"
```

In the benchmark UI, an "Open MLflow Run" link appears as soon as the job uses an HTTP/HTTPS tracking server; the `mlflow.run_url` field in the JSON response is useful for linking from custom tools. For `file:` URIs there is no useful browser URL, so the field remains `null`.

## Evaluation

Place sample images in `data/samples/` and update `data/ground_truth/manifest.jsonl`.

```bash
uv run python -m eval.run --manifest data/ground_truth/manifest.jsonl --samples-dir data/samples --reports-dir eval/reports
```

The report is written to `eval/reports/eval_report_<timestamp>.json`.

## Quality Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app eval tests
uv run pytest
```

## Managing Dependencies (uv)

Install/update and generate lock file:

```bash
uv sync --all-groups
uv lock
```

Add a runtime dependency:

```bash
uv add <package>
```

Add a dev dependency:

```bash
uv add --dev <package>
```

## Word Polygon Detector (optional)

The layout viewer can display word-precise bounding polygons. Set `OCR_WORD_DETECTOR` for this (default: `doctr`).

| Backend | Env value | Installation |
|---|---|---|
| No detector | `none` | — |
| DocTR (default) | `doctr` | included in main dependencies |
| PaddleOCR | `paddleocr` | `pip install ".[paddle]"` or Docker extra `paddle` |

The Docker image installs `paddle` and `osd` extras (`INSTALL_EXTRA=paddle,osd`) and ships `tesseract-ocr` for OSD deskew.

Notes:
- PaddleOCR requires Python 3.12 (no wheels for 3.13).
- PaddleOCR detects running text at line level; polygons are proportionally split into word sub-boxes.
- DocTR natively delivers word-precise polygons with its own recognized text.

## Docker (isolated execution and testing)

### App only (host Ollama)

Install **Ollama on the host**, pull a vision model, then start the **docread app** container (it calls the host at `http://172.17.0.1:11434` by default — `OLLAMA_BASE_URL` in `.env`):

```bash
ollama pull glm-ocr:latest
docker compose up --build -d
```

Open: `http://127.0.0.1:8000`

UI language defaults to English (`APP_LOCALE=en`). Use the **EN / DE** toggle next to the theme control, or set `APP_LOCALE=de` in `.env`. Preference is stored in a cookie and `localStorage`.

An optional **Ollama service** block exists in `docker-compose.yml` but is commented out; uncomment it if you want Ollama inside Compose instead of on the host.

Docker persists downloaded layout models in the `docread_model_cache` volume (`/home/appuser/.cache`).

### App + bundled GLM-OCR (no host Ollama)

Self-contained: **docread** plus a **llama.cpp** GLM-OCR server on the same Docker network (`docker-compose.stack.yml` includes `docker-compose.llamacpp.yml`). First run downloads GGUF weights into the `llamacpp_cache` volume. Vulkan, ROCm, and CUDA variants: [`docs/llamacpp-docker-glm-ocr.md`](docs/llamacpp-docker-glm-ocr.md).

```bash
docker compose -f docker-compose.stack.yml up --build -d
```

### GPU layout (optional)

Default image uses **CPU** PyTorch for layout models (`Dockerfile`). For GPU layout detection, use the compose overlays (see [`docs/docker-pytorch.md`](docs/docker-pytorch.md)):

```bash
# NVIDIA — Dockerfile.cuda (pytorch/pytorch)
docker compose -f docker-compose.yml -f docker-compose.cuda.yml up --build -d

# AMD — Dockerfile.rocm (rocm/pytorch)
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up --build -d
```

Vision LLM inference on GPU uses **llama.cpp** (stack file or `docker-compose.llamacpp.yml`), not PyTorch in the app image.

Inference env vars (`INFERENCE_PROVIDER`, `INFERENCE_BASE_URL`, `INFERENCE_MODEL`, …) are wired in `docker-compose.yml` and read from `.env`.

### Tests

Run isolated quality checks (one-off container, does not need the app running):

```bash
docker compose --profile test run --rm test
```

## License

Licensed under the Apache License 2.0. See [`LICENSE`](LICENSE).

## Author

[HN-Tran](https://github.com/HN-Tran)
