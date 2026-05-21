# Vision LLM inference

docread sends page images and prompts to a **vision-capable language model**. That path is separate from **OCR layout strategy** (`OCR_BACKEND=direct|expert`): inference is *which LLM server* answers; `direct` / `expert` is *how* the document is prepared and segmented.

## Supported providers

| Provider id | Backend | Typical use |
|-------------|---------|-------------|
| `ollama` | [Ollama](https://ollama.com/) `/api/chat` | Default; local or LAN |
| `openai_compatible` | `/v1/chat/completions` + `/v1/models` | llama.cpp server, vLLM, LM Studio, etc. |

Configure the default provider with `INFERENCE_PROVIDER`. Register more at runtime via `INFERENCE_EXTRA_PROVIDERS` (JSON). The UI and `GET /api/inference-providers` list what is available.

## Configuration

| Variable | Default | Notes |
|----------|---------|--------|
| `INFERENCE_PROVIDER` | `ollama` | `ollama` or `openai_compatible` |
| `INFERENCE_BASE_URL` | `http://localhost:11434` | Server root; for OpenAI-compatible APIs often include `/v1` |
| `INFERENCE_MODEL` | `glm-ocr:latest` | Used when the request omits `model` |
| `INFERENCE_API_KEY` | *(empty)* | Bearer token for OpenAI-compatible servers |
| `INFERENCE_VISION_MODELS` | *(empty)* | Comma-separated allowlist for `GET /api/models?vision_only=true` |
| `INFERENCE_VISION_PROBE` | `true` | When the allowlist is empty, probe models (OpenAI-compatible only) |
| `INFERENCE_EXTRA_PROVIDERS` | *(empty)* | JSON map of extra providers (see below) |
| `REQUEST_TIMEOUT_S` | `120` | HTTP timeout for inference calls |

**Legacy env vars:** `OLLAMA_BASE_URL` and `OLLAMA_MODEL` are still read when the matching `INFERENCE_*` values are unset.

**Per request:** form or query field `inference_provider`; `model` as a plain id or `provider/model` (e.g. `openai_compatible/GLM-OCR-Q8_0.gguf`).

### Extra providers (JSON)

```bash
export INFERENCE_PROVIDER=ollama
export INFERENCE_BASE_URL=http://localhost:11434
export INFERENCE_MODEL=glm-ocr:latest
export INFERENCE_EXTRA_PROVIDERS='{"openai_compatible":{"base_url":"http://localhost:8080/v1","vision_models":["GLM-OCR-Q8_0.gguf"]}}'
```

Each entry needs `base_url`; optional `api_key`, `vision_models`, and `vision_probe` (overrides global `INFERENCE_VISION_PROBE` for that entry).

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/inference-providers` | Configured provider ids |
| `GET /api/models` | Models for the default provider |
| `GET /api/models?provider=…&vision_only=true` | Models for one provider, vision filter applied |
| `GET /api/health` | Includes `inference_provider`, `inference_base_url`; legacy `ollama_base_url` / `default_model` mirror the active defaults |

## OpenAI-compatible details

- **List models:** `GET {base}/models` → `data[].id`
- **Chat:** `POST {base}/chat/completions` with `temperature: 0` and a user message (text + `image_url` data URI)
- **Vision filter:** if `INFERENCE_VISION_MODELS` is set, only those ids count as vision models; otherwise heuristics on model names and optional one-pixel probe (`INFERENCE_VISION_PROBE=false` skips probing and treats unknown models as vision-capable)

Step-by-step GLM-OCR with llama.cpp in Docker: [`llamacpp-docker-glm-ocr.md`](llamacpp-docker-glm-ocr.md).

## Implementation note

Code lives under `app/services/inference/` (`VisionLlmClient`, `VisionClientRegistry`, Ollama and OpenAI-compatible clients). OCR pipelines resolve the provider per request and do not embed provider-specific HTTP logic.
