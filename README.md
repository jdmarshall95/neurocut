# NeuroCut

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/jdmarshall95/neurocut/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jdmarshall95/neurocut/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose_ready-2496ED.svg)](docker-compose.yml)

**AI video editing assistant** — drop in a clip and a text brief, get an automatic rough cut as **FCP7 XML** (Premiere / DaVinci) or ready **MP4 clips**.

Built with FastAPI, React, FFmpeg, Whisper-class STT, scene detection, and Google Gemini.

> Keywords: AI video editing · automatic video cutting · FCP7 XML · Whisper transcription · Gemini montage · Premiere plugin

---

## ✨ Features

- **Text-brief montage** — describe the cut in natural language; the LLM returns clips + markers
- **Multi-engine STT** — Whisper / Silero / GigaAM with timestamps and transcript cache
- **Scene detection** — fast low-res / low-FPS proxy for shot boundaries on every job
- **Flexible exports** — FCP7 XML, ZIP of MP4 clips, turnkey stitched render, burned-in subtitles
- **Adobe Premiere Pro CEP plugin** — edit from a local media path (no re-upload)
- **Docker-first** — one command for CPU; GPU override for CUDA Whisper
- **Multi-file sources** — assemble several clips into one editorial timeline

<!-- Demo placeholder
![NeuroCut demo](docs/assets/demo.gif)
-->

## 🏗 Architecture

```
┌─────────────┐     HTTP      ┌──────────────────────────────┐
│  React SPA  │ ────────────► │  FastAPI API (:8000)         │
│   :8501     │               │  /health  /metrics  /docs    │
└─────────────┘               └──────────────┬───────────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    ▼                        ▼                        ▼
               FFmpeg proxy            STT engines              LLM edit plan
            + scene proxy FPS         Whisper/Silero            Gemini/DeepSeek
                                             │
                                             ▼
                                    storage/ (job artifacts)
                         XML · MP4 clips · render · subtitles
```

Diagram asset (optional): place a polished image at [`docs/architecture.png`](docs/architecture.png).  
More detail: [docs/architecture.md](docs/architecture.md).

## 🚀 Quick Start

### Requirements

- [Docker](https://docs.docker.com/get-docker/) (Compose v2)
- [Google Gemini API key](https://aistudio.google.com/apikey) (or DeepSeek for text-only tests)

### CPU (default)

```bash
git clone https://github.com/jdmarshall95/neurocut.git
cd neurocut
cp .env.example .env
# set GEMINI_API_KEY=...

docker compose up --build
```

| Service | URL |
|---------|-----|
| **UI** | http://localhost:8501 |
| **API** | http://localhost:8000 |
| **Swagger** | http://localhost:8000/docs |
| **Metrics** | http://localhost:8000/metrics |

### GPU (NVIDIA)

Requires [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) on the host.

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

This sets `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16`.

### First edit

1. Open http://localhost:8501
2. Choose a task (transcribe, turnkey clip, subtitles, NLE XML, or mobile clips)
3. Upload video + write a short brief
4. Download XML, ZIP clips, or rendered MP4

Stop: `docker compose down` · wipe job storage: `docker compose down -v`  
Local (non-Docker) setup: [CONTRIBUTING.md](CONTRIBUTING.md).

## 🛡 Production Readiness

NeuroCut is wired for operator-friendly deploys, not just a demo script:

| Capability | What you get |
|------------|----------------|
| **CI/CD** | GitHub Actions — lint (Ruff + TypeScript), frontend build, Docker image build checks |
| **Metrics** | Prometheus via `/metrics` — HTTP stats + `neurocut_jobs_total`, `neurocut_processing_duration_seconds` |
| **Logging** | Loguru — colored DEBUG logs locally; structured **JSON** in production (`DEBUG=false`) |
| **Health** | `GET /health` — storage disk space + LLM provider probe (`ok` / `degraded` / `unhealthy`) |
| **Resources** | Compose `mem_limit` / `cpus` on the API service to reduce OOM risk |
| **GPU path** | Optional `docker-compose.gpu.yml` for CUDA Whisper |

## Usage notes

**Premiere plugin:** `./scripts/install_premiere_plugin.sh` → Window → Extensions → NeuroCut.  
See [docs/plugin-development.md](docs/plugin-development.md).

### Useful env vars

| Variable | Purpose | Default |
|----------|---------|---------|
| `GEMINI_API_KEY` | Gemini access | required for Gemini |
| `LLM_PROVIDER` | `auto` / `gemini` / `deepseek` | `auto` |
| `STT_ENGINE` | `whisper` / `silero` / `gigaam` / `auto` | `whisper` |
| `WHISPER_MODEL` | Whisper size | `base` |
| `USE_VIDEO_FOR_LLM` | Upload proxy to Gemini | `false` |
| `SCENE_PROXY_FPS` | Scene-detect FPS | `12` |

Full list: [`.env.example`](.env.example) · [`app/core/config.py`](app/core/config.py).

## Roadmap

- [ ] Broader export: EDL / FCPXML / Resolve markers
- [ ] Stronger hybrid montage (transcript + scenes + optional vision)
- [ ] Quality heuristics for stable / sharp shots
- [ ] Smaller default images + documented GPU CI
- [ ] Public demo dataset + regression fixtures

Track work in [Issues](https://github.com/jdmarshall95/neurocut/issues).

## Contributing

Contributions are welcome — bugs, docs, STT engines, export formats, plugin UX.

1. Read [CONTRIBUTING.md](CONTRIBUTING.md)
2. Follow the [Code of Conduct](CODE_OF_CONDUCT.md)
3. Open a PR with a clear description and smoke-test notes

## Acknowledgments

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / OpenAI Whisper
- [FFmpeg](https://ffmpeg.org/)
- [Google Gemini](https://ai.google.dev/)
- [FastAPI](https://fastapi.tiangolo.com/) · [React](https://react.dev/) · [Vite](https://vitejs.dev/)
- GigaAM / Silero communities for offline STT options

## License

Licensed under the [MIT License](LICENSE).

```
Copyright (c) 2026 NeuroCut Contributors
```
