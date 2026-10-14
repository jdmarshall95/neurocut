# NeuroCut

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/jdmarshall95/neurocut/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jdmarshall95/neurocut/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose_ready-2496ED.svg)](docker-compose.yml)

<p align="center">
  <a href="docs/assets/neurocut-demo.mp4">
    <img src="docs/assets/neurocut-demo.gif" alt="NeuroCut pipeline walkthrough — upload, audio extraction, transcription, scene detection, AI edit, render, result" width="720">
  </a>
</p>

**AI video editing assistant** — drop in a clip and a text brief, get an automatic rough cut as **FCP7 XML** (Premiere / DaVinci) or ready **MP4 clips**.

Built with FastAPI, React, FFmpeg, Whisper-class STT, scene detection, and Google Gemini.

---

## Features

- **Text-brief montage** — describe the cut in natural language; the LLM returns clips + markers
- **Multi-engine STT** — Whisper / Silero / GigaAM with timestamps and transcript cache
- **Scene detection** — fast low-res / low-FPS proxy for shot boundaries on every job
- **Flexible exports** — FCP7 XML, ZIP of MP4 clips, turnkey stitched render, burned-in subtitles
- **Adobe Premiere Pro CEP plugin** — edit from a local media path (no re-upload)
- **Docker-first** — one command for CPU; GPU override for CUDA Whisper
- **Multi-file sources** — assemble several clips into one editorial timeline

## Pipeline walkthrough

A real end-to-end run on a public test clip — the [Sintel trailer](https://media.w3.org/2010/05/sintel/trailer.mp4)
(52 s, 854×480, H.264 + AAC) — submitted through the UI with `export_mode = render` and the brief:

> *"Cut a 30 second cinematic teaser: keep the emotional narration and the most dramatic wide shots, drop slow dialogue scenes."*

The pipeline finished in **~35 s** and produced a stitched `neurocut_render.mp4` with **4 clips**, **2 markers**
and `analysis_mode = speech`.

| # | Stage | What happens | Cold-run time |
|---|-------|--------------|---------------|
| 1 | `extracting_audio` | FFmpeg builds a 480p proxy and extracts the audio track | ~15 s |
| 2 | `transcribing` | Whisper-class STT with word timestamps (content-addressable cache) | ~5 s |
| 3 | `analyzing_scenes` | Low-FPS / low-res scene detection for shot boundaries | ~0.2 s |
| 4 | `ai_editing` | Gemini turns the brief + transcript into an edit plan (clips + markers) | ~2 s |
| 5 | `rendering_clip` | Clips are stitched into one turnkey MP4 | ~13 s |

<details>
<summary><b>Stage-by-stage screenshots</b></summary>

<table>
  <tr>
    <td width="50%"><img src="docs/assets/ui-01-landing.png" alt="Landing page — task selector, dropzone and editing brief"></td>
    <td width="50%"><img src="docs/assets/ui-02-upload.png" alt="Video and editing brief attached, ready to build"></td>
  </tr>
  <tr>
    <td><b>1 · Audio</b><br><img src="docs/assets/ui-03-audio.png" alt="Stage 1 — extracting audio"></td>
    <td><b>2 · Transcription</b><br><img src="docs/assets/ui-04-transcribing.png" alt="Stage 2 — transcribing speech"></td>
  </tr>
  <tr>
    <td><b>3 · Scene detection</b><br><img src="docs/assets/ui-05-scenes.png" alt="Stage 3 — analyzing scenes"></td>
    <td><b>4 · AI edit</b><br><img src="docs/assets/ui-06-ai-editing.png" alt="Stage 4 — Gemini builds the edit plan"></td>
  </tr>
  <tr>
    <td><b>5 · Rendering clip</b><br><img src="docs/assets/ui-07-rendering.png" alt="Stage 5 — rendering the turnkey clip"></td>
    <td><b>Result</b><br><img src="docs/assets/ui-08-result.png" alt="Result card — stitched clip, metrics and edit plan"></td>
  </tr>
</table>

</details>

> Reproduce the run: `docker compose up --build`, open http://localhost:8501, drop in any MP4 with speech,
> type a brief and press **Build clip**.

## Architecture

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

More detail: [docs/architecture.md](docs/architecture.md).

## Quick Start

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

## Ops

| Capability | Detail |
|------------|--------|
| **CI** | GitHub Actions — Ruff, TypeScript, frontend build, Docker image build |
| **Metrics** | Prometheus `/metrics` — HTTP + `neurocut_jobs_total`, `neurocut_processing_duration_seconds` |
| **Logging** | Loguru (DEBUG locally; JSON when `DEBUG=false`) |
| **Health** | `GET /health` — disk + LLM probe (`ok` / `degraded` / `unhealthy`) |
| **Resources** | Compose `mem_limit` / `cpus` on the API service |
| **GPU** | Optional `docker-compose.gpu.yml` for CUDA Whisper |

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
