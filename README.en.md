# Video Transcript API

> An asynchronous video transcription service built on Python 3.11+, with multi-platform downloading, dual transcription engines, LLM-powered text processing and enterprise features.

[中文 README](README.md) | **English**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.101+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-yellow.svg)](LICENSE)

![Transcription result page](docs/images/overview.jpg)

---

## Features

- **Multi-platform support**: YouTube, Bilibili, Douyin, Xiaohongshu, WeChat Channels and X (Twitter) (via MediaResolverAPI), Xiaoyuzhou podcast, Apple Podcast. A factory selects the right downloader automatically.
- **Dual transcription engines**: [CapsWriter ASR Server](https://github.com/zlxlabs/CapsWriter-ASR-Server) protocol v2 (general transcription) + FunASR (speaker diarization).
- **LLM text processing**: automatic ASR error calibration, proper-noun correction, speaker inference with per-speaker sampling and confidence-based degradation, content summarization.
- **Controllable processing depth**: the per-task `processing_options` switches decide whether to calibrate and summarize. Layered cache artifacts only ever grow, and repeated requests reuse the layers that already exist.
- **Honest status model**: calibration (`full`/`partial`/`none`/`disabled`) and summary (`generated`/`skipped_short`/`failed`/`pending`/`disabled`) states are passed through end to end instead of being masked by placeholder strings.
- **Enterprise features**: two-tier cache (SQLite + filesystem), multi-user management, audit log (including LLM token usage statistics), multi-channel notifications (WeCom + Feishu), task history browser.
- **Risk control**: sensitive-word detection, multi-strategy text redaction, automatic risk-model switching.

## External dependencies

- [TikHub API key for audio/video parsing and downloading (affiliate link)](https://user.tikhub.io/register?referral_code=YArXsaWi)
- [funasr_spk_server: the API exposed by a FunASR server. Transcribes audio/video, separates speakers and merges consecutive turns of the same person.](https://github.com/zj1123581321/funasr_spk_server)
- [CapsWriter ASR Server: a LAN speech recognition service. This project talks to it through the official SDK using protocol v2 and no longer uses hand-written v1 frames. Field and error-code semantics follow the protocol document.](https://github.com/zlxlabs/CapsWriter-ASR-Server/blob/master/docs/reference/protocol.md)
- [youtube_download_api: a YouTube download service that acts as an optional alternative backend to yt-dlp.](https://github.com/zj1123581321/youtube_download_api) (optional)
- [MediaResolverAPI](https://github.com/zlxlabs/MediaResolverAPI): a central resolution service turning short-video / WeChat Channels URLs into watermark-free direct links plus metadata. It takes over Douyin, Xiaohongshu, WeChat Channels and X (Twitter) resolution (see the [usage guide](docs/guides/media_resolver.md); for X it automatically picks the lowest-bitrate variant for speed).
- An OpenAI-compatible API, for example DeepSeek.

---

## Quick start

### Requirements

- Python 3.11+
- FFmpeg
- A transcription server ([CapsWriter ASR Server protocol v2](https://github.com/zlxlabs/CapsWriter-ASR-Server) and/or FunASR)

### Local installation

```bash
# Clone the repository
git clone <repository-url>
cd video-transcript-api

# Install dependencies (with uv)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Configure the service
cp config/config.example.jsonc config/config.jsonc
# Edit config.jsonc and fill in api.auth_token, tikhub.api_key and the like
# Optional: route Douyin/Xiaohongshu through MediaResolverAPI (WeChat Channels and X
#   require this switch to be on). Set downloaders.use_media_resolver=true and
#   configure the media_resolver section
#   (usage guide: docs/guides/media_resolver.md)

# Start
uv run python main.py --start
```

Before starting you can run a side-effect-free configuration preflight. It connects to no external service, migrates no database and starts no thread:

```bash
uv run python main.py --check-config --config config/config.jsonc
```

### Docker deployment

```bash
# Prepare the configuration
cp config/config.example.jsonc config/config.jsonc

# Build and start locally (uses the fixed dev tag; not for production deployment)
cd docker/
docker compose up -d --build
```

**Docker image**: [`ghcr.io/zj1123581321/video-transcript-api`](https://ghcr.io/zj1123581321/video-transcript-api)

The image bundles ffmpeg, BBDown and yt-dlp, so nothing else needs installing.

`docker/docker-compose.yml` publishes the container's port `8000` on host port `8200`, so a local Docker deployment answers on `http://localhost:8200` (the examples further down use `http://localhost:8000`, which is the port the service itself listens on when you run it directly with `uv run`).

Production deployments must never push to any registry or use a mutable tag (including `latest`). The build script refuses a dirty working tree, and only from a clean commit does it generate a unique tag from the 12-character Git SHA and push it to GHCR (the public image build entry point; it does not deploy). The local `video-transcript-api:latest` on a deployment machine is not a registry mutable tag: it is the machine-local alias produced by the deployment script when it retags an immutable ACR SHA image. It exists only on the deployment machine, compose and image reconciliation refer to that local name, and it never enters any registry.

```bash
./docker/push_to_ghcr.sh
```

Production deployment is handled by the automated pipeline: pushing `main` triggers `.github/workflows/deploy.yml` (build → ACR → deployment host → health probe → deploy); after a fix to the workflow itself, re-dispatch it manually with `workflow_dispatch`. Deployment details and disaster-recovery fallbacks are in [docker/DEPLOY.md](docker/DEPLOY.md); the configuration file lives at `<deploy-dir>/config/config.jsonc`.

> **Note**: CapsWriter ASR Server (protocol v2) and FunASR must be deployed separately. Inside Docker the service addresses in the configuration cannot be `localhost`; use the host IP or `host.docker.internal`. Protocol documentation: [CapsWriter ASR protocol v2](https://github.com/zlxlabs/CapsWriter-ASR-Server/blob/master/docs/reference/protocol.md).

---

## Minimal configuration

Copy `config/config.example.jsonc` to `config/config.jsonc` and adjust at least the following. The example file carries bilingual (Chinese / English) comments on every field, so it doubles as the reference for all other options.

```jsonc
{
    // "zh-CN" (default) or "en". Controls the Web UI wording and the output
    // language of generated content (summary, detailed notes, chapters).
    // WeCom and Feishu notifications do not follow this switch yet.
    "language": "en",

    "api": {
        "port": 8000,
        "host": "0.0.0.0",
        "auth_token": "your-auth-token-here"   // clients send this as a Bearer token
    },
    "tikhub": {
        "api_key": "your-tikhub-api-key-here"
    },
    "llm": {
        "api_key": "your-llm-api-key-here",
        "base_url": "https://your-api.com/v1"  // up to /v1 only, no /chat/completions
    },
    "capswriter": {
        "server_url": "ws://localhost:6016"    // protocol v2
    },
    "funasr_spk_server": {
        "server_url": "ws://localhost:8767"
    }
}
```

Set `"language": "en"` for an English user-facing experience: the Web UI wording and the generated summary, detailed notes and chapter titles come out in English. The key accepts `"zh-CN"` or `"en"`; the default is `"zh-CN"`, and any other value makes startup fail. WeCom and Feishu notifications keep their own fixed templates for now.

Validate the result before starting:

```bash
uv run python main.py --check-config --config config/config.jsonc
```

## Usage

### Submit a transcription task

```bash
curl -X POST "http://localhost:8000/api/transcribe" \
  -H "Authorization: Bearer your-auth-token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=xxx",
    "use_speaker_recognition": true
  }'
```

### Transcribe only, without calibration or summarization

`processing_options` controls the processing depth per task. `calibrate`, `summarize` and `infer_speaker_names` all default to `true` (the historical behaviour):

```bash
curl -X POST "http://localhost:8000/api/transcribe" \
  -H "Authorization: Bearer your-auth-token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=xxx",
    "processing_options": {
      "calibrate": false,
      "summarize": false,
      "infer_speaker_names": false
    }
  }'
```

With all three switches `false` no LLM call is made. Layered cache artifacts only grow: a later request for the same video with `calibrate: true` or `infer_speaker_names: true` runs only the missing layers that have not passed validation, and an existing transcript is never downloaded again. Full semantics: [processing depth switches](docs/features/processing_options.md).

### Query task status

```bash
curl -X GET "http://localhost:8000/api/task/{task_id}" \
  -H "Authorization: Bearer your-auth-token"
```

### Web interface

- **Submit a task**: `GET /add_task_by_web`
- **View a result**: `GET /view/{view_token}` — an unguessable public read-only share capability; write operations still require authentication
- **Task history**: `GET /static/history.html` — search by date, platform, channel and keyword, read tracking, summary preview
- **Export a file**: `GET /export/{view_token}/{type}` (`calibrated`, `summary`, `notes`, `transcript`)

The home page, the task history page and the result page share one browser access token, stored under the canonical key `vta_bearer_token` and read by a single Bearer authentication module. The result page and its `GET` export links are an unguessable public read-only capability: whoever holds the link can read that result. Submitting transcriptions, querying private tasks and history, and the write actions on the result page (re-calibrate, re-summarize, generate detailed notes) are still protected by `Authorization: Bearer <access token>`. Only ever type the access token into a browser you trust; never put it into a URL, a share link or a log.

### API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/transcribe` | POST | Submit a transcription task (supports the `processing_options` depth switches) |
| `/api/task/{task_id}` | GET | Query task status |
| `/api/recalibrate` | POST | Re-calibrate (the only forced-redo exception, it ignores the layered-cache protection; a missing summary is still regenerated, but to rerun only the summary use `/api/resummarize`) |
| `/api/resummarize` | POST | Regenerate only the summary (skips download, transcription, calibration and chapters, reusing the calibrated text) |
| `/api/generate_notes` | POST | Generate detailed notes per existing chapter asynchronously (only adds the notes cache layer; does not rewrite calibration, summary or chapters) |
| `/api/audit/stats` | GET | Call statistics, including aggregated LLM token usage (prompt/completion/total tokens per stage) |
| `/api/audit/calls` | GET | Call records |
| `/api/audit/history` | GET | Terminal task history from audit.db (status accepts only `success`, `failed`, `all`; supports filtering, pagination and keyword search), including processing state and `content_expired` |
| `/api/audit/filter-options` | GET | Filter options (webhook/platform/channel lists) |
| `/api/audit/summary` | GET | Task summary preview (first 300 characters), returning `summary_status` based on the honest status model |
| `/api/users/profile` | GET | Current user information |
| `/view/{view_token}` | GET | Result view page |
| `/view/{view_token}?raw=calibrated` | GET | Plain-text export |
| `/view/{view_token}?page=calibrated` | GET | HTML page export |
| `/view/{view_token}?raw=notes` | GET | Detailed notes as plain text (available once generated) |
| `/view/{view_token}?page=notes` | GET | Detailed notes as an HTML page (available once generated) |
| `/export/{view_token}/{type}` | GET | File download |

---

## Project structure

```
video-transcript-api/
├── src/video_transcript_api/
│   ├── api/              # FastAPI service, routes, dependency injection
│   ├── downloaders/      # Multi-platform downloaders (factory pattern)
│   ├── transcriber/      # Transcription engines (CapsWriter + FunASR)
│   ├── llm/              # LLM processing engine (coordinator - processor - core components)
│   ├── cache/            # Cache system (SQLite + filesystem)
│   └── utils/            # Utilities (logging, notifications, risk control, user management, ...)
├── tests/                # Test suite
├── docs/                 # Detailed documentation
├── config/               # Configuration files
├── docker/               # Docker deployment files
└── main.py               # Entry point
```

---

## Documentation

Detailed documentation lives under [docs/](docs/) (currently written in Chinese):

- **Architecture**: [System architecture and module breakdown](docs/architecture.md)
- **Guides**: [Multi-channel notifications (WeCom + Feishu)](docs/guides/notification.md) · [Multi-user setup](docs/guides/multi_user_setup.md) · [MediaResolverAPI integration (Douyin/Xiaohongshu/WeChat Channels/X)](docs/guides/media_resolver.md)
- **API guides**: [FunASR](docs/guides/api/funasr_spk_server_client_api.md) · [YouTube](docs/guides/api/youtube_client_guide.md) · [BBDown](docs/guides/api/bbdown_guide.md)
- **Development**: [LLM engineering guide](docs/development/llm/engineering_guide.md) · [Concurrency](docs/development/concurrency.md) · [Logging](docs/development/logging.md)
- **Features**: [Processing depth switches (processing_options)](docs/features/processing_options.md) · [Raw/page export](docs/features/raw_export.md) · [Download URL and metadata override](docs/features/source_url_and_metadata_override.md)

---

## Tests

```bash
make test
```

`make test` is the local gate: it runs `uv sync --frozen` and then `uv run --frozen pytest -q tests`, so it discovers the whole `tests/` tree and skips only `tests/manual/` (the explicitly opt-in suite).

---

## License

Released under the **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)**. Any **non-commercial** use, study, modification and distribution is permitted; **all commercial use is prohibited** (including internal use for profit-making business, resale or commercial integration). Use by non-profit institutions such as academic, educational, public-interest and government organisations counts as permitted. See [LICENSE](LICENSE) for details.
