[English](README.md) · [Deutsch](README_DE.md)

# docread

<p align="center">
  <a href="https://github.com/HN-Tran/docread/actions/workflows/ci.yml"><img src="https://github.com/HN-Tran/docread/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/HN-Tran/docread/releases"><img src="https://img.shields.io/github/v/release/HN-Tran/docread?label=release" alt="Release"></a>
  <a href="https://github.com/HN-Tran/docread/blob/master/LICENSE"><img src="https://img.shields.io/github/license/HN-Tran/docread" alt="Lizenz"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="docker-compose.yml"><img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose"></a>
</p>

<p align="center"><strong>Selbst gehostete Dokument-OCR mit Vision-Sprachmodellen</strong></p>

<p align="center">
  Scans, Fotos und PDFs auf eigener Infrastruktur auswerten — mit Browser-UI,
  produktionsreifer REST-API und Drop-in-Kompatibilität zu Azure Document Intelligence.
</p>

## Warum docread?

Die meisten OCR-Lösungen zwingen zu Kompromissen: Cloud-API (Kosten pro Seite, Daten verlassen das Netz) oder zusammengeklebte Open-Source-Tools, die bei schiefen Kamerafotos, Tabellenrastern und mehrseitigen PDFs scheitern. **docread ist eine selbst gehostete Anwendung**, die moderne Vision-LLMs lokal ausführt, unordentliche Scans vor der OCR begradigt und trotzdem die APIs spricht, die bestehende Tools bereits erwarten.

## Auf einen Blick

| Merkmal | Details |
|---------|---------|
| **Eigener Stack, eigene Daten** | Ollama, vLLM, llama.cpp oder jeder OpenAI-kompatible Vision-Server — kein Vendor-Lock-in, kein Upload in die Cloud. |
| **Zwei Modi, eine Installation** | **Direct** (`backend=direct`) für schnelle Ganzseiten-OCR; **Dev** (`backend=expert`) für Layout-Regionen, Tabellen, Wortboxen und Regions-Deskew bei schwierigen Scans. |
| **Für echte Scans gebaut** | Automatisches Deskew und Vierteldrehung (Tesseract OSD, Projektionsvarianz, gekachelte Feinkorrektur) — für A4-Ränder, gebogene Buchfotos und kleine Inhaltsinseln auf großen Seiten. |
| **Sehen, was das Modell sah** | Interaktive Vorschau mit Layout-Overlays, Wortpolygonen, Markdown-Ausgabe und Neigungsmetadaten pro Region. |
| **Genauigkeit intern belegen** | Direktvergleich mit Azure, Google Vision oder einer anderen docread-Instanz; Batch-Benchmark mit CER/WER bei Referenztext; optional MLflow. |
| **Drop-in für Azure-Workflows** | `prebuilt-read` Sync-/Async-Endpunkte, kompatibel mit Azure Document Intelligence (ehemals Form Recognizer). |
| **Datenhoheit & Datenschutz** | Self-hosted — keine Pflicht-Cloud-OCR, keine Telemetrie an die Projekt-Maintainer; geeignet für On-Premises, Private Cloud und air-gapped Betrieb unter eigener Kontrolle. |

## Funktionen

### Direct-Modus — schnelle Ganzseiten-OCR (`backend=direct`)

Vision-Modell auf die ganze Seite, Text in Sekunden. Ideal für saubere PDFs, schnelle Extraktion und strukturiertes JSON mit eigenem Schema. Funktioniert mit jedem Modell, das das Inference-Backend bereitstellt (GLM-OCR, Qwen-VL, …).

### Dev-Modus — layoutbewusstes Dokumentverständnis (`backend=expert`)

Bei schwierigeren Seiten als flache Scans läuft eine vollständige Pipeline:

- **Layout-Erkennung** — Textblöcke, Titel, Tabellen, Abbildungen (Standard: PP-DocLayoutV3).
- **Regions-OCR** — jeder Crop einzeln ans Vision-Modell für bessere Treffer auf dichten Seiten.
- **Intelligentes Deskew** — kardinale Seitenausrichtung plus Feinkorrektur pro Region bei Kameraufnahmen und Tabellenstreifen.
- **Tabellenzellen** — optional Microsoft Table Transformer für Zell-BBoxen.
- **Wortpolygone** — DocTR oder PaddleOCR, eingeblendet in der Vorschau.
- **Text-Anker** — Fuzzy-Match der Regions-OCR zurück auf Ganzseitentext.

### Evaluation & Benchmarking

- **Vergleich** (`POST /api/compare`) — docread gegen Azure, Google Vision, Peer-Instanz oder beliebigen HTTP-Text-Endpunkt; Token-Diff und optional CER/WER.
- **Benchmark** (`/benchmark` oder `POST /api/benchmark`) — viele Dateien × viele Modelle/Engines mit Aggregatmetriken und CSV-Export.
- **Offline-Eval** (`eval/run`) — Regression auf festem Samplesatz mit Manifest.

### Integrationen

- **REST-API** mit Swagger (`/docs`), ReDoc (`/redoc`) und OpenAPI-JSON.
- **Web-UI** unter `/` — Drag-and-Drop, Layout/Wort/Markdown/Diff-Ansichten, EN/DE.
- **Azure Document Intelligence Kompatibilität** — `prebuilt-read` Sync- und Async-Analyse.
- **Docker Compose** — App-Container (CPU-Standard; optional NVIDIA/AMD-GPU für Layout); Stack-Datei bündelt docread + llama.cpp GLM-OCR. Host-Ollama über Standard-Env.

## Datenschutz & Datenhoheit

docread richtet sich an Organisationen, die Bürgerakten, Vorgänge oder interne Unterlagen **nicht** an Cloud-OCR-Dienste Dritter senden dürfen — **Kommunen, Behörden, Gesundheitswesen, Recht, regulierte Wirtschaft**.

| Anforderung | Was docread bietet |
|-------------|-------------------|
| **Datenresidenz (EU / DSGVO)** | Verarbeitung auf **Ihrer** Infrastruktur. Sie bestimmen Standort von Anwendung und Vision-Modell (EU-Rechenzentrum, behördliche Private Cloud, Offline-Standort). |
| **Kein Vendor-Lock-in, keine Telemetrie** | Die Anwendung sendet **keine** Dokumente oder Nutzungsdaten an die Projekt-Maintainer. Ausgehender Traffic nur durch **Ihre** Konfiguration: Inference-Server, optionale Vergleichs-Engines, einmalige Modell-Downloads unter Ihrer Kontrolle. |
| **Air-gap / isolierte Netze** | Nach dem Cachen von Modellen und Layout-Gewichten offline betreibbar. Inference über lokales Ollama oder llama.cpp im gleichen Netzsegment — zur OCR-Zeit kein Internet nötig. |
| **Cloud-OCR schrittweise ersetzen** | Azure-kompatible Endpunkte: bestehende Integrationen zeigen auf eine **On-Premises**-docread-Instanz statt auf eine öffentliche Cloud-API. |
| **Betriebskontrolle** | Sie steuern Aufbewahrung: Async-Analyse (`ANALYZE_STORE_DIR`), Benchmark-TTL, Logs, TLS und Zugriff über Reverse Proxy und IAM. |
| **Transparenz** | Apache 2.0, prüfbarer Quellcode, Standard-Docker-Deployment auf VMs oder Kubernetes nach Ihrem Sicherheitsniveau. |

**Was wir nicht behaupten:** docread ist **Software**, kein zertifiziertes Compliance-Produkt. Es gibt kein „DSGVO-Zertifikat“ für eine App. Wir behaupten **kein** ISO 27001, SOC 2, BSI IT-Grundschutz oder Branchenfreigaben — das hängt von **Ihrem** Betrieb, Prozessen und ggf. DSFA / Rechtsprüfung ab. Optionale Vergleichs- und Benchmark-Funktionen können **Dritt-APIs** (Azure, Google) aufrufen; in Produktion deaktivieren oder nur in isolierten Nicht-Produktions-Umgebungen nutzen.

**Typisches Behörden-Setup:** docread plus lokales Vision-Modell auf verwalteter Hardware, in Produktion keine externe OCR, Vergleichsmodus höchstens in einer isolierten Testumgebung.

## Anforderungen

- Python 3.12+
- `uv` 0.10+
- Ein vision-fähiges Modell auf dem Inference-Backend (Standard Ollama, oder OpenAI-kompatibler Server)

## Setup

```bash
uv sync --all-groups
```

### Konfiguration

[`.env.example`](.env.example) nach `.env` kopieren für Docker Compose. Die Standardwerte entsprechen `app/config.py`, sofern nicht anders angegeben.

#### Inference (Vision-LLM)

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `INFERENCE_PROVIDER` | `ollama` | `ollama` oder `openai_compatible` (vLLM, llama.cpp, …). Details: [`docs/inference-providers.md`](docs/inference-providers.md). |
| `INFERENCE_BASE_URL` | `http://localhost:11434` | API-Basis-URL. Fallback: `OLLAMA_BASE_URL`. |
| `INFERENCE_MODEL` | `glm-ocr:latest` | Standardmodell, wenn der Request kein `model` setzt. Fallback: `OLLAMA_MODEL`. |
| `INFERENCE_API_KEY` | *(leer)* | Optionales Bearer-Token für OpenAI-kompatible Server. |
| `INFERENCE_VISION_MODELS` | *(leer)* | Kommagetrennte Allowlist für `GET /api/models?vision_only=true`. |
| `INFERENCE_VISION_PROBE` | `true` | OpenAI-kompatibles `/models` abfragen, wenn die Allowlist leer ist. |
| `INFERENCE_EXTRA_PROVIDERS` | *(leer)* | JSON-Karte zusätzlicher Provider. |
| `DEFAULT_TOKEN_LIMIT` | `16384` | Standard-Ollama-`num_ctx` / Kontextlimit (`1..128000`). |
| `REQUEST_TIMEOUT_S` | `120` | HTTP-Timeout für Inference-Aufrufe (Sekunden). |
| `VERIFY_SSL` | `false` | TLS-Zertifikatsprüfung für Inference-HTTP-Clients. |

Legacy-Aliase `OLLAMA_BASE_URL` und `OLLAMA_MODEL` funktionieren weiter. Pro Request: Formularfeld `inference_provider`; Modell als `provider/model` (z. B. `openai_compatible/my-vlm`).

OpenAI-kompatibles Beispiel (GLM-OCR per Docker: [`docs/llamacpp-docker-glm-ocr.md`](docs/llamacpp-docker-glm-ocr.md)):

| Variable | Beispiel |
|----------|----------|
| `INFERENCE_PROVIDER` | `openai_compatible` |
| `INFERENCE_BASE_URL` | `http://localhost:8080/v1` |
| `INFERENCE_MODEL` | `GLM-OCR-Q8_0.gguf` |

#### OCR-Backends

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `OCR_BACKEND` | `expert` | `direct` (Ganzseiten-OCR) oder `expert` (Dev: Layout + Regions-OCR). UI: **Direct** / **Dev**. |
| `OCR_EXPERT_ENABLE_LAYOUT` | `true` | Layout-Erkennung im Dev-Modus. |
| `OCR_EXPERT_LAYOUT_MODEL` | `PaddlePaddle/PP-DocLayoutV3_safetensors` | Hugging-Face-Layout-Modell (`HFLayoutDetector`). |
| `OCR_EXPERT_LAYOUT_DEVICE` | `auto` | `auto`, `cpu`, `cuda` oder `mps` für Layout-Inferenz. |
| `OCR_EXPERT_LAYOUT_THRESHOLD` | *(pro Modell)* | Optionale globale Konfidenz (`0..1`); pro Request überschreibbar. |
| `OCR_EXPERT_LAYOUT_MAX_DIM` | `1800` | Lange Kante für Layout-Detektion (Boxen zurück auf Volauflösung). |
| `OCR_EXPERT_TABLE_TRANSFORMER` | `false` | Microsoft Table Transformer für Tabellenzellen. |
| `OCR_EXPERT_PER_REGION_OCR` | `true` | OCR pro Layout-Region (aus = nur Layout, schneller). |
| `OCR_EXPERT_TEXT_ANCHOR` | `true` | Regions-OCR per Fuzzy-Match an Ganzseiten-Text anbinden. |
| `OCR_EXPERT_TEXT_ANCHOR_THRESHOLD` | `60` | RapidFuzz-Schwellwert fürs Text-Anchoring. |
| `OCR_EXPERT_COMPARE_INCLUDE_DETECTOR_ONLY` | `false` | Detektor-only-Wörter im Compare-Diff einbeziehen. |
| `OCR_WORD_DETECTOR` | `doctr` | Wort-Polygone: `none`, `paddleocr` oder `doctr`. |

#### Scan-Deskew

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `DESKEW_ENABLED` | `true` | Seiten vor OCR/Layout begradigen. |
| `DESKEW_PAGE_CARDINAL` | `true` | Vierteldrehung auf Content-BBox-Probe (Rand-Scans). |
| `DESKEW_OSD` | `1` | Tesseract-OSD auf der Probe (benötigt `pytesseract`; im Docker-Image). |
| `DESKEW_OSD_MIN_CONFIDENCE` | `1.0` | Mindest-OSD-Konfidenz für Kardinal-Hinweis. |
| `DESKEW_FINE_SCAN_DIM` | `2400` | Max. Dimension für gekachelte Fein-Skew-Suche. |
| `DESKEW_MIN_ANGLE_DEG` | `0.5` | Korrekturen unter diesem Winkel ignorieren (Grad). |
| `DESKEW_CONTENT_BBOX_MAX_FILL` | `0.72` | Ganzseiten-Probe, wenn Tintenfüllung darüber liegt. |
| `DESKEW_QUARTER_TURN` | `auto` | Erzwingen: `90`, `270`, `-90` oder `auto`. |
| `DESKEW_DEBUG` | `0` | Deskew-Entscheidungen in Logs und OCR-`warnings` protokollieren. |

#### Upload-Limits & Preprocessing

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `MAX_UPLOAD_BYTES` | `8388608` | Maximale Upload-Größe (8 MiB). |
| `MAX_IMAGE_DIM` | `3600` | Max. lange Kante nach dem Laden (Pixel). |
| `OCR_BINARIZED_MIN_DIM` | `1800` | 1-bit-/Graustufen-Eingaben mindestens auf diese Größe hochskalieren. |
| `ANALYZE_STORE_DIR` | `/tmp/docread-analyze-results` | Persistierte Azure-kompatible Analyze-Ergebnisse. |

#### Compare-Presets (optional)

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `AZURE_PRESET_LABEL` | *(leer)* | Label für Azure-Schnellbutton in der UI. |
| `AZURE_PRESET_ENDPOINT` | *(leer)* | Azure-Endpoint-URL für dieses Preset. |
| `AZURE_PRESET_LAYOUT_ENDPOINT` | *(leer)* | Optionales zweites Preset (Layout-Modell). |
| `AZURE_PRESET_KEY` | *(leer)* | Serverseitiger Key, wenn die UI die Preset-URL ohne Key aufruft. |

#### Benchmark & MLflow

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `BENCHMARK_MAX_FILES` | `50` | Max. Dateien pro Benchmark-Job. |
| `BENCHMARK_MAX_RUNNERS` | `5` | Max. Runner (Modelle + Engines) pro Job. |
| `BENCHMARK_JOB_TTL_S` | `3600` | In-Memory-Aufbewahrung von Jobs (Sekunden). |
| `MLFLOW_TRACKING_URI` | *(leer)* | z. B. `http://mlflow:5000` oder `file:./mlruns`; leer = aus. |
| `MLFLOW_EXPERIMENT_NAME` | `docread` | MLflow-Experimentname. |

#### Anwendung

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `APP_LOCALE` | `en` | UI-Sprache: `en` oder `de`. |
| `APP_BASE_PATH` | *(leer)* | URL-Präfix hinter einem Reverse-Proxy. |
| `HOST` | `127.0.0.1` | Bind-Adresse für `uvicorn`. |
| `PORT` | `8000` | Port für `uvicorn`. |

### Eingabe-Preprocessing und Deskew

Gemeinsame Schritte (`app/services/ocr_pipeline.py`, `app/services/deskew.py`):

- RGBA/LA und transparente Palette-PNGs werden auf **weißem** Hintergrund komponiert (vermeidet schwarze Defaults, die schwarzen Text auf transparentem Hintergrund unsichtbar machen würden).
- Bitonale (`1`) und Graustufen (`L`) Eingaben werden auf mindestens `OCR_BINARIZED_MIN_DIM` Pixel (Standard 1800) hochskaliert, damit Modelle „l"/„I"/„1" zuverlässiger unterscheiden können.
- Bei `DESKEW_ENABLED=true` (Standard) wird jede Seite **vor** der OCR begradigt. Vierteldrehungen nutzen eine Content-BBox-Probe (hilfreich bei A4-Scans mit Rand); Fein-Skew nutzt gekachelte Projektionssuche auf großen Seiten. Optional `DESKEW_OSD=1` ergänzt Tesseract-OSD auf der Probe (benötigt `pytesseract`, im Docker-Image über das `osd`-Extra enthalten).
- PDF-`/Rotate`-Metadaten werden beim Rendern in Pixel übernommen, bevor Deskew läuft.

**Dev-Backend** (`app/services/document_pipeline.py`):

- Zuerst Seiten-Deskew; der Layout-Detektor sieht das korrigierte Preview (herunterskaliert auf `OCR_EXPERT_LAYOUT_MAX_DIM`, Standard 1800, Boxen danach auf volle Auflösung für Crops).
- Regionen unter 40 % der Seitenfläche können zusätzlich ein Regions-Deskew auf dem Crop vor der OCR erhalten.
- `page_infos[].angle` und Azure `pages[].angle` melden die **angewendete CCW-Korrektur** der Seite (0 wenn keine).
- Pro Layout-Region optional: `angle` (Neigung im **Original**-Scan), `preview_angle` (= Original − Seitenkorrektur), `deskew_correction_ccw` (zusätzliche CCW auf dem Regions-Crop).

OSD lokal installieren: `uv sync --extra osd` oder `pip install '.[osd]'`.

## Starten

```bash
uv run uvicorn app.main:app --reload
```

Öffnen: `http://127.0.0.1:8000`

## API

Interaktive Referenz (maßgeblich für Request-Felder und Typen): [`/docs`](http://127.0.0.1:8000/docs) (Swagger UI), [`/redoc`](http://127.0.0.1:8000/redoc) und [`/openapi.json`](http://127.0.0.1:8000/openapi.json). Strukturierte Schema-Namen: `GET /api/schemas`.

`POST /api/ocr` akzeptiert entweder `multipart/form-data` oder einen rohen Body mit
`Content-Type: application/octet-stream`.

Zusätzlich gibt es eine Azure-Read-kompatible Oberfläche mit den Endpunkten der Document Intelligence Read-Container-API:

- `GET /status`
- `GET /ready`
- `GET /ContainerReadiness`
- `GET /ContainerLiveness`
- `POST /formrecognizer/documentModels/prebuilt-read:syncAnalyze`
- `POST /formrecognizer/documentModels/prebuilt-read:analyze`
- `GET /formrecognizer/documentModels/prebuilt-read/analyzeResults/{resultId}`

Kompatibilitäts-Hinweise:

- `api-version=2022-08-31` ist erforderlich.
- `application/octet-stream` und `application/json` mit `{"urlSource":"..."}` werden akzeptiert.
- `:analyze` liefert `202` plus `Operation-Location`; die Verarbeitung läuft im Hintergrund und wird im Analyze-Store für Polling bereitgestellt.
- Analyze-Ergebnisse werden zusätzlich im Dateisystem unter `ANALYZE_STORE_DIR` persistiert, damit Polling nach einem Prozessneustart auf demselben Volume weiter funktioniert.
- `pages` und `stringIndexType` werden akzeptiert; `pages` filtert aktuell nur das Antwort-Payload, nicht die eigentliche OCR-Ausführung.
- `modelId` ist auf `prebuilt-read` begrenzt.
- `pages`, `paragraphs`, `lines`, `words` und `spans` werden jetzt best-effort aus OCR-Text und Layoutdaten gefüllt. `textElements` bleibt dabei eine pragmatische Annäherung, keine vollständige Grapheme-Cluster-Implementierung.
- `pages[].angle` meldet die angewendete **CCW-Korrektur** der Seite bei aktivem Deskew (wie natives `page_infos[].angle`, nicht Azures Uhrzeigersinn-Semantik).
- `pages[].words` nutzt — sobald `OCR_WORD_DETECTOR=doctr|paddleocr` aktiv ist und der Detektor Wort-Polygone geliefert hat — die echten Detektor-Boxen (gleiche Daten wie der „Wörter"-Tab im Browser) statt der synthetischen Wort-Wrapper aus den Layout-Regionen. Ohne Detektor bleibt der bisherige Fallback erhalten.

#### `POST /api/ocr`

Pflicht: Datei-Bytes — Multipart-Feld `file` oder roher Body `application/octet-stream`. Bei `mode=structured` zusätzlich `schema_name`. Alle übrigen Felder (`backend`, `model`, `task`, `expert_*`, …) sind optionale Overrides; die vollständige Liste steht in der OpenAPI.

Raw-Upload: dieselben optionalen Parameter als Query-Strings. Formaterkennung per Signatur (`png`, `jpeg`, `webp`, `gif`, `tiff`, `pdf`, `doc`, `docx`); Word wird via LibreOffice nach PDF konvertiert.

```powershell
Invoke-RestMethod -Method POST `
  -Uri 'https://HOST/api/ocr?backend=direct&mode=plain' `
  -ContentType 'application/octet-stream' `
  -InFile 'C:\path\scan.tiff'
```

**Verhalten (in OpenAPI nicht wiederholt)**

- **Eingaben:** PDF → alle Seiten; animierte GIFs → gesampelte Frames (Standard 8, Obergrenze `gif_max_frames`). `describe_image` bei GIFs in einem Storyboard-Aufruf.
- **Backends:** `direct` — Vision-LLM pro Seite/Frame, Text im Tab **Text**. `expert` (Dev) — Layout-Pipeline bei `mode=plain` und `task=ocr_text`, sonst Fallback auf Direct. Dev kann `markdown` liefern (UI-Vorschau), `text` bleibt roh.
- **Dev-Layout:** Hugging-Face-Objekterkennung über `OCR_EXPERT_LAYOUT_MODEL` / `expert_layout_model` (Gewichte, die Sie konfigurieren; nicht mit docread ausgeliefert). Achsenparallele `bbox_2d`-Regionen; optional Table-Transformer-`cells` in Tabellenregionen.

Beispiel-Antwort:

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
  "markdown": "# Titel\n\n...",
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

## Vergleich mit externer OCR-Engine

`POST /api/compare` führt unsere OCR-Pipeline parallel zu einer externen Engine
aus und liefert Diff, Side-by-Side-Metriken und (optional) CER/WER gegen einen
Referenztext. `GET /api/compare/engines` listet die unterstützten Engines.

**Unterstützte Engines** (`engine`-Form-Feld):

| `engine` | Konfigurations-Felder | Bemerkungen |
|---|---|---|
| `azure` | `azure_endpoint`, `azure_key` | Azure Form Recognizer / Document Intelligence prebuilt-read. Nutzt asynchrones Polling. |
| `self_peer` | `peer_base_url`, `peer_backend` | Postet die Datei an `<peer_base_url>/api/ocr` einer anderen Instanz dieser App — sinnvoll, um zwei Konfigurationen oder Modellversionen direkt zu vergleichen. |
| `google_vision` | `google_api_key` | Google Cloud Vision REST (`DOCUMENT_TEXT_DETECTION`). |
| `plain_text` | `plain_text_url`, optional `plain_text_method`, `plain_text_field`, `plain_text_auth_header`, `plain_text_auth_value` | Generischer Endpoint, der entweder reinen Text oder `{"text": "..."}` liefert. Liefert keine Bounding-Boxen, Diff bleibt textbasiert. |

**Optionale Parameter** (engine-unabhängig):

- `reference_text`: Ground-Truth-Text. Wenn gesetzt, ergänzt die Antwort einen `metrics.reference`-Block mit echten CER, WER und Token-F1 für beide Seiten.
- `expert_*` und `backend`: greifen für unsere eigene OCR-Seite (siehe oben).
- `expert_compare_include_detector_only`: bezieht zusätzlich Wort-Polygone des Detektors in den Diff ein, die kein Layout-Token getroffen haben.

**Metriken im Response** (`metrics`-Block):

- `intrinsic`: Tokens, Zeichen, Ø Konfidenz, Latenz pro Seite.
- `comparison`: paarweise Δ Zeichen, Δ Wörter (normalisierte Levenshtein-Distanz — bewusst _nicht_ CER/WER, da keine Seite Ground Truth ist), Token-Jaccard, Token-Precision/Recall/F1.
- `reference`: nur wenn `reference_text` mitgeliefert wurde — echte CER, WER, Token-F1 pro Seite.

**Azure-Preset** (Browser-Workflow):
Sind `AZURE_PRESET_LABEL`, `AZURE_PRESET_ENDPOINT` und `AZURE_PRESET_KEY` gesetzt,
erscheint im Compare-Formular ein Schnellbutton mit dem Label. Schickt der
Browser eine Anfrage an genau diese Endpoint-URL ohne API-Key, ergänzt der
Server den Schlüssel intern — der geheime Wert verlässt nie das Backend.

**Warum kein AWS Textract?**
AWS Textract ist bewusst _nicht_ enthalten, weil es eine SigV4-Signatur
braucht und damit entweder `boto3` (~10 MB) oder eine eigene Signatur-
Implementierung erfordert. Da keine konkrete AWS-Anforderung besteht,
bleibt die Abhängigkeit draußen. Bei Bedarf:

1. `boto3` als optionalen Extra in `pyproject.toml` ergänzen (analog zum bestehenden `paddle`-Extra).
2. `app/services/compare_engines/aws_textract.py` nach dem Muster der anderen Engines schreiben (Klasse mit `name`/`label`/`async def analyze`).
3. In `app/services/compare_engines/registry.py` registrieren.

## Batch-Benchmark

`/benchmark` (UI) bzw. `POST /api/benchmark` führen N Dateien gegen M Runner
aus — Runner sind entweder lokale Ollama-Modelle oder externe Engines aus
dem Compare-Flow. Pro Zeile werden Token-/Zeichen-Anzahl, Latenz und
(falls Referenztext mitgegeben wurde) CER/WER/Token-F1 berechnet. Aggregat
pro Runner liefert Durchschnitt + Standardabweichung.

### Wie es intern funktioniert

Benchmark-Jobs liegen in einem **prozesslokalen** `BenchmarkJobStore` (`app/services/benchmark.py`): `asyncio.Lock` + In-Memory-`dict`. Nicht über Replikas geteilt; nach Neustart weg, sofern Sie nicht CSV/MLflow exportiert haben.

- **Worker:** `POST /api/benchmark` liefert sofort `{job_id}`; `run_benchmark_job` läuft als `asyncio.create_task` und aktualisiert `job.rows` direkt.
- **Sequentiell:** (Datei × Runner)-Paare nacheinander, damit Ollama-Latenzen vergleichbar bleiben (kein paralleles lokales Inference).
- **Fortschritt:** Poll `GET /api/benchmark/{job_id}` (UI ~2 s). Zeilen: `pending → running → done|error`. Optional `POST /api/benchmark/{job_id}/cancel` setzt `cancelled`.
- **Aufbewahrung:** nach Abschluss (oder Abbruch) wird der Job nach `BENCHMARK_JOB_TTL_S` (Standard 3600) automatisch entfernt. `DELETE /api/benchmark/{job_id}` entfernt sofort.
- **Export:** `GET /api/benchmark/{job_id}/csv`; optional MLflow Parent/Child-Runs bei `MLFLOW_TRACKING_URI` (siehe unten).

Azure-kompatible `:analyze`-Jobs nutzen einen **separaten** Dateisystem-Store (`ANALYZE_STORE_DIR`), nicht das Benchmark-Dict.

### Job-Lifecycle

```
POST   /api/benchmark                    → { job_id }
GET    /api/benchmark                    → { jobs: [...] }
GET    /api/benchmark/{job_id}           → Job-Status + Fortschritt
POST   /api/benchmark/{job_id}/cancel    → laufenden Job abbrechen
GET    /api/benchmark/{job_id}/csv       → CSV-Export
DELETE /api/benchmark/{job_id}           → Job sofort löschen
```

Hard-Caps konfigurierbar via `BENCHMARK_MAX_FILES` (Standard 50) und
`BENCHMARK_MAX_RUNNERS` (Standard 5).

### Per REST steuerbar (curl-Beispiel)

Browser-UI ist optional — die API ist self-contained:

```bash
# 1. Job submitten (zwei Dateien, je ein Referenztext, zwei Modelle, plus Azure)
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

# 2. Pollen bis fertig
while true; do
  status=$(curl -s "http://localhost:8000/api/benchmark/$JOB" | jq -r .status)
  echo "$status"
  [[ "$status" == "done" || "$status" == "failed" ]] && break
  sleep 2
done

# 3. Ergebnis als CSV holen
curl -s "http://localhost:8000/api/benchmark/$JOB/csv" -o "benchmark-$JOB.csv"

# 4. Aus dem Server-Speicher entfernen (optional)
curl -s -X DELETE "http://localhost:8000/api/benchmark/$JOB"
```

`models` und `engines` sind kommagetrennte Listen. Mindestens einer der
beiden Werte muss nicht leer sein. `references` muss in derselben
Reihenfolge wie `files` mitgegeben werden — leerer String = keine Referenz
für diese Datei.

Engine-spezifische Felder (nur die ausgewählten Engines werden bedient):

| Engine | Erforderliche Felder |
|---|---|
| `azure` | `azure_endpoint`, `azure_key` |
| `self_peer` | `peer_base_url`, optional `peer_backend`, `peer_model` |
| `google_vision` | `google_api_key` |
| `plain_text` | `plain_text_url`, optional `plain_text_method`, `plain_text_field`, `plain_text_auth_header`, `plain_text_auth_value` |
| `local_models` | (nicht über Engines — siehe `models`) |

### Antwort-Schema (`GET /api/benchmark/{job_id}`)

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

### MLflow-Tracking (optional)

Wenn `MLFLOW_TRACKING_URI` gesetzt ist UND `mlflow` installiert wurde
(`pip install '.[mlflow]'`), schreibt der Worker zusätzlich:

- einen Parent-Run pro Job mit Aggregat-Metriken (`<runner>.mean_cer`, …),
- pro (Datei, Runner) einen verschachtelten Child-Run mit Parametern,
  Metriken und `hypothesis.txt` / `reference.txt` als Artefakten.

Konfiguration:

```bash
export MLFLOW_TRACKING_URI=http://mlflow:5000   # oder file:./mlruns
export MLFLOW_EXPERIMENT_NAME=docread          # default: "docread"
```

Im Benchmark-UI erscheint ein „MLflow-Run öffnen"-Link, sobald der Job
einen HTTP/HTTPS-Tracking-Server nutzt; das `mlflow.run_url`-Feld in der
JSON-Antwort taugt fürs Verlinken aus eigenen Tools. Bei `file:`-URIs gibt
es keine sinnvolle Browser-URL, dann bleibt das Feld `null`.

## Evaluation

Beispielbilder nach `data/samples/` legen und `data/ground_truth/manifest.jsonl` aktualisieren.

```bash
uv run python -m eval.run --manifest data/ground_truth/manifest.jsonl --samples-dir data/samples --reports-dir eval/reports
```

Der Report wird unter `eval/reports/eval_report_<timestamp>.json` geschrieben.

## Qualitätsprüfungen

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app eval tests
uv run pytest
```

## Abhängigkeiten verwalten (uv)

Installieren/Aktualisieren und Lock-Datei erzeugen:

```bash
uv sync --all-groups
uv lock
```

Runtime-Abhängigkeit hinzufügen:

```bash
uv add <package>
```

Dev-Abhängigkeit hinzufügen:

```bash
uv add --dev <package>
```

## Wort-Polygon-Detektor (optional)

Der Layout-Viewer kann wortgenaue Bounding-Polygone anzeigen. Dafür wird `OCR_WORD_DETECTOR` gesetzt (Standard: `doctr`).

| Backend | Env-Wert | Installation |
|---|---|---|
| Kein Detektor | `none` | — |
| DocTR (Standard) | `doctr` | in den Haupt-Dependencies enthalten |
| PaddleOCR | `paddleocr` | `pip install ".[paddle]"` bzw. Docker-Extra `paddle` |

Das Docker-Image installiert die Extras `paddle` und `osd` (`INSTALL_EXTRA=paddle,osd`) und enthält `tesseract-ocr` für OSD-Deskew.

Hinweise:
- PaddleOCR erfordert Python 3.12 (keine Wheels für 3.13).
- PaddleOCR detektiert Fließtext auf Zeilenebene; die Polygone werden proportional in Wort-Teilboxen aufgeteilt.
- DocTR liefert nativ wortgenaue Polygone mit eigenem erkanntem Text.

## Docker (isoliertes Ausführen und Testen)

### Nur App (Host-Ollama)

**Ollama auf dem Host** installieren, Vision-Modell laden, dann den **docread**-Container starten (Standard: Host unter `http://172.17.0.1:11434` — `OLLAMA_BASE_URL` in `.env`):

```bash
ollama pull glm-ocr:latest
docker compose up --build -d
```

Öffnen: `http://127.0.0.1:8000`

UI-Sprache standardmäßig Englisch (`APP_LOCALE=en`). Umschalten über **EN / DE** neben dem Theme oder `APP_LOCALE=de` in `.env`. Die Wahl wird in Cookie und `localStorage` gespeichert.

Ein optionaler **Ollama-Service** in `docker-compose.yml` ist auskommentiert; zum Betrieb in Compose statt auf dem Host einkommentieren.

Layout-Modelle landen im Volume `docread_model_cache` (`/home/appuser/.cache`).

### App + gebündeltes GLM-OCR (ohne Host-Ollama)

Alles in Docker: **docread** plus **llama.cpp** mit GLM-OCR im gleichen Netz (`docker-compose.stack.yml` bindet `docker-compose.llamacpp.yml` ein). Beim ersten Start werden GGUF-Gewichte in `llamacpp_cache` geladen. Varianten Vulkan/ROCm/CUDA: [`docs/llamacpp-docker-glm-ocr.md`](docs/llamacpp-docker-glm-ocr.md).

```bash
docker compose -f docker-compose.stack.yml up --build -d
```

### GPU-Layout (optional)

Standard-Image nutzt **CPU**-PyTorch für Layout-Modelle (`Dockerfile`). Für GPU-Layout die Compose-Overlays (siehe [`docs/docker-pytorch.md`](docs/docker-pytorch.md)):

```bash
# NVIDIA — Dockerfile.cuda
docker compose -f docker-compose.yml -f docker-compose.cuda.yml up --build -d

# AMD — Dockerfile.rocm
docker compose -f docker-compose.yml -f docker-compose.rocm.yml up --build -d
```

Vision-LLM-Inference auf der GPU läuft über **llama.cpp** (Stack-Datei oder `docker-compose.llamacpp.yml`), nicht über PyTorch im App-Image.

Inference-Env-Variablen (`INFERENCE_PROVIDER`, `INFERENCE_BASE_URL`, `INFERENCE_MODEL`, …) stehen in `docker-compose.yml` und `.env`.

### Tests

Isolierte Qualitätsprüfungen (einmaliger Container, App muss nicht laufen):

```bash
docker compose --profile test run --rm test
```

## Lizenz

Apache License 2.0. Siehe [`LICENSE`](LICENSE).

## Autor

[HN-Tran](https://github.com/HN-Tran)
