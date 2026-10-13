# Architecture

## High-level flow

```
Upload (1..N videos) + prompt
        │
        ▼
 MediaProcessor ──► audio.wav + proxy_480p.mp4 + proxy_scenes.mp4
        │
        ▼
 STTService ──────► transcript.json (cached by audio hash)
        │
        ▼
 SceneDetector ───► visual_timeline.json (always, via low-FPS proxy)
        │
        ▼
 AIAnalyzer ──────► edit_plan.json (Gemini / DeepSeek, usually text-only)
        │
        ├── XMLGenerator      → neurocut_export.xml
        ├── ClipExporter      → clips ZIP
        ├── VideoRenderer     → turnkey MP4
        └── SubtitleBurner    → burned-in subtitles
```

## Packages

| Path | Role |
|------|------|
| `app/api/` | FastAPI routes (jobs, plugin, downloads) |
| `app/core/` | Settings, Gemini/DeepSeek clients |
| `app/services/` | Pipeline stages |
| `app/models/` | Pydantic schemas (`EditPlan`, timelines) |
| `app/utils/` | Timecode, sources manifest, normalize |
| `frontend/` | React SPA (Vite + Tailwind) |
| `premiere/NeuroCut/` | CEP panel |

## Job storage layout

Each job id under `storage/<job_id>/` typically contains:

- `sources/` + `sources_manifest.json` (multi-cam / multi-clip assembly)
- `transcript.json`, `visual_timeline.json`, `edit_plan.json`
- `pipeline_progress.json` (+ analysis / transcription progress)
- Export artifacts (`neurocut_export.xml`, `neurocut_clips.zip`, …)

## Decision log

See [adr/](adr/) for why text-out Gemini models, scene proxies, and Apache-2.0 were chosen.
