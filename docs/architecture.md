# Architecture

## High-level flow

Orchestrator: `PipelineRunner` (`app/services/pipeline.py`). All stages are **sequential**. Export modes are **mutually exclusive**.

```
Upload (1..N videos) + prompt + export_mode
        │
        ▼
 MediaProcessor
   · single → original + audio.wav + proxy_480p.mp4 + proxy_scenes.mp4
   · multi  → sources/* assembly + sources_manifest.json (+ same top-level artifacts)
        │
        ▼
 Transcript branch
   · uploaded transcript → skip STT
   · has audio           → STTService → transcript.json (cache by audio hash)
   · no audio            → empty transcript, force analysis_mode=visual
        │
        ▼
 analysis_mode = speech | visual  (sparse / missing speech → visual)
        │
        ▼
 SceneDetector ──► visual_timeline.json  (always, via proxy_scenes.mp4)
        │
        ▼
 AIAnalyzer ──────► edit_plan.json  (Gemini / DeepSeek; usually text-only)
        │
        ├── export_mode=xml    → XMLGenerator   → neurocut_export.xml
        ├── export_mode=clips  → ClipExporter   → neurocut_clips.zip
        ├── export_mode=render → VideoRenderer  → neurocut_render.mp4
        └── export_mode=plugin → plan only for Premiere CEP
```

`SubtitleBurner` is **not** part of `PipelineRunner`. It runs via a separate API after a job has a transcript / plan.

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

- `sources/` + `sources_manifest.json` (multi-clip assembly)
- `audio.wav`, `proxy_480p.mp4`, `proxy_scenes.mp4`
- `transcript.json`, `visual_timeline.json`, `edit_plan.json`
- `pipeline_progress.json` (+ analysis / transcription progress)
- One export artifact per mode (`neurocut_export.xml`, `neurocut_clips.zip`, or `neurocut_render.mp4`)

## Decision log

See [adr/](adr/) for why text-out Gemini models, scene proxies, and Apache-2.0 were chosen.
