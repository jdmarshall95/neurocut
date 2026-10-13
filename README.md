# NeuroCut

**AI video editing assistant** — drop in a clip and a text brief, get an automatic rough cut as **FCP7 XML** (Premiere / DaVinci) or ready **MP4 clips**. Powered by Whisper-class STT, scene detection, and Google Gemini.

[![CI](https://github.com/jdmarshall95/neurocut/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jdmarshall95/neurocut/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![API docs](https://img.shields.io/badge/API-OpenAPI%20%2F%20Swagger-green.svg)](http://localhost:8000/docs)

> Keywords: AI video editing · automatic video cutting · FCP7 XML · Whisper transcription · Gemini montage · Premiere plugin

---

## Overview

Manual rough cuts eat hours: scrubbing timelines, marking takes, exporting for mobile editors. **NeuroCut** turns “video + editing brief” into a machine-readable edit plan and exports you can open in a real NLE or share as clips.

```
Video + brief  →  STT + scene detection  →  LLM edit plan  →  XML / MP4 clips / turnkey render
```

<!-- DEMO: replace with a 30–60s GIF or hosted MP4 -->
<!-- ![NeuroCut demo](docs/assets/demo.gif) -->

<p align="center"><em>📷 Place a demo GIF/screenshot here: <code>docs/assets/demo.gif</code></em></p>

<!-- SCREENSHOTS:
docs/assets/ui-upload.png   — upload + task picker
docs/assets/ui-progress.png — pipeline progress
docs/assets/ui-result.png   — download XML / clips
-->

## Features

- **Text-brief montage** — describe the cut in natural language; Gemini builds clips + markers
- **Speech transcription** — Whisper / Silero / GigaAM with timestamps; transcript cache
- **Scene detection** — fast low-res / low-FPS proxy for shot boundaries
- **Exports** — FCP7 XML, ZIP of MP4 clips, turnkey stitched render, burned-in subtitles
- **Adobe Premiere Pro CEP plugin** — edit from a local media path (no re-upload)
- **Docker-first** — `docker compose up --build` and open the UI

## Demo

| Asset | Status |
|-------|--------|
| Screen recording (30–60s) | TODO → `docs/assets/demo.gif` |
| Annotated UI screenshots | TODO → `docs/assets/` |
| Sample input + edit_plan.json | TODO → `docs/examples/` |

See the [demo assets plan](docs/demo-assets.md).

## Why Open Source?

NeuroCut should be a **practical tool for editors and developers**, not a black-box SaaS:

- Inspect and fork the montage pipeline (STT → scenes → LLM → export)
- Swap STT engines and export formats without waiting for a vendor roadmap
- Run offline-friendly STT (GigaAM / Silero) where privacy matters
- Learn and teach how AI rough-cutting actually works end-to-end

Commercial use is welcome under **Apache License 2.0** (attribution required; patent grant included).

## Installation

### Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (recommended)
- [Google Gemini API key](https://aistudio.google.com/apikey)

### Quick start

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

Stop: `docker compose down` · wipe job storage: `docker compose down -v`

Local (non-Docker) setup: [CONTRIBUTING.md](CONTRIBUTING.md).

## Usage

1. Open http://localhost:8501
2. Pick a task: **transcribe**, **turnkey clip**, **subtitles**, **NLE XML**, or **mobile clips**
3. Upload video (MP4 / MOV / MKV / AVI / WebM) — multi-file montage supported
4. For montage, write a short brief, e.g. *“Keep 3–4s clean talking-head beats, drop filler”*
5. Download transcript, XML, ZIP clips, or rendered MP4

**Premiere plugin:** `./scripts/install_premiere_plugin.sh` → Window → Extensions → NeuroCut.  
Details: [docs/plugin-development.md](docs/plugin-development.md).

### Useful env vars

| Variable | Purpose | Default |
|----------|---------|---------|
| `GEMINI_API_KEY` | Gemini access | required |
| `LLM_PROVIDER` | `auto` / `gemini` / `deepseek` | `auto` |
| `STT_ENGINE` | `whisper` / `silero` / `gigaam` / `auto` | `whisper` |
| `WHISPER_MODEL` | Whisper size | `base` |
| `USE_VIDEO_FOR_LLM` | Upload proxy to Gemini | `false` (text-out models) |
| `SCENE_PROXY_FPS` | Scene-detect FPS | `12` |

Full list: [`.env.example`](.env.example) · [`app/core/config.py`](app/core/config.py).

## Architecture

```
┌─────────────┐     HTTP      ┌─────────────┐
│  React SPA  │ ────────────► │   FastAPI   │
│   :8501     │               │    :8000    │
└─────────────┘               └──────┬──────┘
                                     │
              FFmpeg · STT · Scene detect · Gemini/DeepSeek
                                     │
                              storage/ (volume)
```

More detail: [docs/architecture.md](docs/architecture.md) · historical notes: [IMPLEMENTATION.md](IMPLEMENTATION.md).

## Roadmap

- [ ] Broader export: EDL / FCPXML / Resolve markers
- [ ] Stronger hybrid montage (transcript + scenes + optional vision models)
- [ ] Quality filters for “no blur / stable shot” heuristics
- [ ] GPU Whisper path and smaller default images
- [ ] Public demo dataset + regression fixtures
- [ ] Multi-language UI

Track work in [Issues](../../issues). Ideas welcome.

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
- Everyone who files issues, shares cuts, and sends PRs

## License

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for third-party attributions.

```
Copyright 2026 NeuroCut Contributors
```
