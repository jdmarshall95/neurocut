# NeuroCut — Project Roadmap

## Implemented Phases

### Phase 1: Setup & Media Processing
- Initialize FastAPI and Streamlit.
- Implement `media_processor.py`:
  - Function to extract audio to `.wav` (16kHz, mono).
  - Function to downscale video to 480p `.mp4` (H.264).
- *Constraint:* Use `subprocess` or `ffmpeg-python`. Ensure output paths are inside `storage/`.

### Phase 2: Transcription
- Implement `transcriber.py` using `faster-whisper`.
- *Constraint:* Output must be a list of dictionaries: `[{"start": 1.5, "end": 3.2, "text": "Hello world"}, ...]`. Do not use word-level if it's too heavy, segment-level is fine for MVP, but timestamps must be precise.

### Phase 3: LLM Analysis (The Core)
- Implement `ai_analyzer.py`.
- **Prompt Strategy:**
  1. Pass the editing brief.
  2. Pass the transcript with timestamps.
  3. Pass the proxy video (using Gemini's video upload API).
- *Output Constraint:* The LLM MUST output strictly valid JSON. Use Pydantic or `instructor` library to enforce the schema.

### Phase 4: NLE Export (FCP7 XML)
- Implement `xml_generator.py`.
- *Strategy:* Do NOT build XML from scratch using `xml.etree`. It's too complex for Premiere. Use **Final Cut Pro 7 XML** format. Premiere Pro and DaVinci Resolve import FCP7 XML perfectly, and it is 10x simpler to template.
- Create `fcp7_template.xml.j2`.
- Write logic to convert `start_sec` and `end_sec` into FCP7 timecode format or frame counts (assume 24fps or 30fps, make it configurable).
- Inject clips into `<track>` and markers into `<marker>` tags in the XML.

### Phase 5: Frontend & Integration
- Build `streamlit_app.py`.
- UI: File uploader, Text area for prompt, "Generate" button.
- Show status: "Extracting audio...", "Transcribing...", "AI is editing...", "Generating XML...".
- Provide download button for the final `.xml`.

### Phase 6: CapCut Export (draft_content.json)
- Implement `capcut_generator.py`.
- **Strategy:** Use existing open-source parser (e.g., `capcut-draft-parser`) OR create Jinja2 template based on reverse-engineered format.
- **Key conversions:**
  - Convert `start_sec` → microseconds (`start_sec * 1_000_000`)
  - Generate unique UUIDs for each track, segment, material
  - Create `materials.videos` entry pointing to original uploaded file
  - Create `segments` entries in `tracks` with correct `target_timerange` and `source_timerange`
  - Convert `markers` to `materials.texts` (CapCut doesn't have native markers, use text overlays at specific times as workaround)
- **Output:** Save as `draft_content.json` inside a folder structure that CapCut Desktop recognizes (`storage/{job_id}/capcut_export/draft_content.json`) plus a `neurocut_capcut.zip` archive.
- **Status:** Implemented in a separate branch `capcut` (not merged). API: `POST /jobs/{job_id}/export/capcut`, `GET /jobs/{job_id}/export/capcut/download`.

---

## Additional Phases (Implemented after MVP)

### Phase 7: Clip Export via FFmpeg (ZIP)
- Implemented `clip_exporter.py` — an alternative to XML for mobile editors (CapCut, InShot, etc.).
- Export branching: mode `xml` (for NLE) and mode `clips` (ready-made cuts).
- **What it does:**
  - Reads `edit_plan.json`, cuts each clip with FFmpeg (H.264 + AAC, `+faststart`, `yuv420p`).
  - Stores clips in `clips_export/`, adds `manifest.json` (timecodes, track, reason).
  - Packs everything into `neurocut_clips.zip`.
- **API:** `POST /jobs/{job_id}/export/clips`, `GET /jobs/{job_id}/export/clips/download`; parameter `export_mode` in `POST /jobs/generate`.
- **UI:** export format switcher, separate ZIP download button.

### Phase 8: Visual Analysis & Silent Video Handling
- Implemented `scene_detector.py` + model `visual_timeline.py`.
- **Problem:** videos without speech (or almost no speech) broke the pipeline at the audio extraction / empty transcript stage.
- **Solution:**
  - `media_processor.py` checks for audio track presence (ffprobe). No audio → `audio.wav` is not created, proxy is assembled with `-an`.
  - `transcriber.py`: `allow_silent` and `record_no_audio` — empty transcript instead of crash, Whisper is not loaded unnecessarily.
  - If there is no speech or it is too sparse (`is_sparse_speech`), the pipeline switches to visual mode.
  - `scene_detector.py`: FFmpeg `select='gt(scene,threshold)'` finds scene changes → `visual_timeline.json`.
  - `ai_analyzer.py`: separate system prompt for visual editing (composition, dynamics, scene boundaries).
- **Config:** `scene_threshold`, `min_scene_duration_sec`.
- **UI/pipeline:** new stage `analyzing_scenes` ("Analyzing scenes...").

### Phase 9: Model Cascade & Timecode Reliability
- **Gemini model cascade** (`config.py`, `ai_analyzer.py`): fallback from best to worst.
  - `resolved_gemini_models` / `GEMINI_MODEL_PRIORITY`; on 429/404/403/503 or model unavailability — automatic switch to the next one.
  - Correct handling of `google.genai.errors.ClientError` (field `code`, not `status_code`).
- **Timecode normalization** (`edit_plan_normalize.py`):
  - Format approved in prompt and JSON schema: absolute seconds with one decimal place (`1.0`, `12.5`).
  - Post-processing: rounding to 0.1s, protective auto-scaling if the model returned fractions instead of seconds.
- Refined `edit_plan.py` (field descriptions) and correction-prompt for invalid JSON.

### Phase 10: Containerization & Portability
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `README.md`.
- Running API + Streamlit, FFmpeg inside the image, mounting `storage/`.

### Phase 11: Portable Media Paths in XML
- Implemented `media_path.py`.
- **Problem:** absolute `pathurl` in FCP7 XML broke when moving to another machine.
- **Solution:**
  - `source_media.json` stores the original filename.
  - `xml_generator.py` writes relative `file://./<name>` — media sits next to the XML after unpacking.

### Phase 12: Extract STT as a Standalone Service
- Implemented `stt_service.py` — decoupled speech-to-text from the LLM pipeline.
- **What it does:**
  - `STTService.transcribe()` wraps Whisper with content-addressable caching.
  - Cache key: SHA-256 of first 1 MB of audio + duration → `storage/transcripts/{hash}.json`.
  - Repeated uploads of the same audio return cached transcript instantly.
  - `STTService.parse_transcript_file()` — import user SRT/VTT/JSON transcripts.
  - `STTService.store_uploaded_transcript()` — persist uploaded transcript to job and/or cache.
- **API:**
  - `POST /jobs/{job_id}/transcribe` — transcription only (existing endpoint, now uses `STTService` + cache).
  - `GET /jobs/{job_id}/transcript` — fetch transcript with metadata (`source`, `cached`, `file_hash`).
  - `POST /transcripts` — upload ready-made SRT/VTT/JSON (optional `job_id`, `file_hash`).
- **Config:**
  - `USE_VIDEO_FOR_LLM` (default `true`) — when `false`, Gemini receives only text (cheaper).
  - `SKIP_STT_IF_TRANSCRIPT_PROVIDED` (default `true`) — skip Whisper if user uploaded transcript.
  - `STT_CACHE_ENABLED` (default `true`).
- **Refactors:**
  - `ai_analyzer.py`: optional `segments_override`, text-only mode when `USE_VIDEO_FOR_LLM=false`.
  - `pipeline.py` and `_run_transcription_job`: use `STTService`, respect uploaded transcripts.
  - `transcriber.py`: added `load_transcript()` for reading saved job transcripts.

### Phase 13: Pluggable STT Engines (Silero + GigaAM)
- Implemented `transcriber_silero.py` and `transcriber_gigaam.py` — drop-in STT engines
  behind `STTService`, each mirroring the `Transcriber` interface (`transcribe`,
  `save_transcript`, `load_transcript`, `record_no_audio`, `to_dicts`).
- **Silero** (`transcriber_silero.py`):
  - Silero VAD segments speech + Silero STT decodes each chunk → timestamped segments.
  - Languages: **en, de, es, ua only** (Silero STT does not cover all locales).
  - Lazy `torch` import + `torch.hub` caching (`lru_cache`, `trust_repo=True`).
- **GigaAM** (`transcriber_gigaam.py`) — offline GigaAM STT:
  - `sherpa-onnx` + GigaAM NeMo-CTC (upstream package under `gigaam-ru/`).
  - Silero VAD (ONNX) segments speech; each chunk decoded by GigaAM → timestamped segments.
  - Reads 16 kHz mono PCM WAV directly (our `audio.wav`), lazy `sherpa_onnx` import + recognizer cache.
  - Runs on CPU with competitive quality for supported locales.
- **Engine selection** (`STTService._resolve_engine`):
  - `STT_ENGINE=whisper` (default) | `silero` | `gigaam` | `auto`.
  - `auto`: GigaAM-preferred locales when installed; en/de/es/ua → Silero; else Whisper.
  - **Graceful fallback:** if an engine's deps/models are missing or it fails at runtime,
    falls back to Whisper.
- **Config:** `STT_ENGINE`, `SILERO_LANGUAGE` (default `en`), `GIGAAM_MODEL_DIR`, `GIGAAM_VAD_MODEL`,
  `GIGAAM_NUM_THREADS`, `GIGAAM_MAX_SEGMENT_SEC`.
- **Deps:** optional `requirements-silero.txt` (`torch`, `torchaudio`, `omegaconf`) and
  `requirements-gigaam.txt` (`sherpa-onnx`) — base image stays light.
- **Models:** `scripts/download_gigaam.py` fetches GigaAM CTC + Silero VAD (~230 MB).
- **Docker:** build-args `INSTALL_SILERO=1` / `INSTALL_GIGAAM=1` install deps and preload/download
  models into `/app/.cache` (outside the `storage` volume so it survives mounts).
- **Refactor:** extracted `write_transcript_json` / `read_transcript_json` helpers in
  `transcriber.py` so all engines share persistence.

---

## Planned Phases

### Phase 12: Extract STT as a Standalone Service
- **Status:** ✅ Implemented (see "Additional Phases" above).

### Phase 13: Pluggable offline STT (Silero / GigaAM)
- **Status:** ✅ Implemented (see "Additional Phases" above). Optional engines:
  **GigaAM** (sherpa-onnx NeMo-CTC) and **Silero** (en/de/es/ua); cloud engines remain future options.
- **Problem:** A single STT backend is not ideal for all locales and deploy constraints:
  - Whisper is strong but heavier on CPU/GPU for some workloads.
  - Operators may want fully offline engines with smaller footprints.
  - Language coverage differs across open models.
- **Solution:** Pluggable `STT_ENGINE` with Whisper default and optional local engines:
  - **Silero Models:** open-source local STT for selected languages.
  - **GigaAM + sherpa-onnx:** offline CTC STT package for additional locales.
  - **`auto`:** route by language hint to the best available installed engine.
- **Implementation:**
  - `transcriber_silero.py` / `transcriber_gigaam.py` behind `stt_service.py`.
  - Config: `STT_ENGINE` (`whisper` | `silero` | `gigaam` | `auto`).
  - Optional Docker build args to install deps and preload models.
- **Benefits:**
  - Faster local processing where specialized engines fit.
  - Better control over privacy (no cloud STT required).
  - Flexible fallbacks when optional deps are missing.
- **Validation:** Compare WER / latency on a held-out clip set per engine.

### Phase 14: Adobe Premiere Pro Plugin (Seamless Integration) — **Implemented**

- **CEP panel** (`premiere/NeuroCut/`): HTML/JS UI inside Premiere, ExtendScript host (`host/NeuroCut.jsx`).
- **Plugin API** (`/plugin/*`): zero-upload workflow — `local_path` + `prompt` instead of file upload.
- **Pipeline mode** `export_mode=plugin`: completes after AI edit plan; skips XML/clips export.
- **Timeline layout** (`app/utils/timeline_layout.py`): precomputed clip positions for ExtendScript.
- **Local path security**: `PLUGIN_ALLOWED_ROOTS` or `PLUGIN_ALLOW_ANY_LOCAL_PATH` (dev).
- **Reference media mode**: `PLUGIN_COPY_MEDIA_TO_STORAGE=false` — FFmpeg reads user's file in place.
- **Install script**: `scripts/install_premiere_plugin.sh`.

**Workflow:**
1. User selects local video in Premiere panel.
2. Panel POSTs path + prompt to FastAPI.
3. Pipeline: extract audio → STT → Gemini → edit plan JSON.
4. Panel polls status, fetches `/plugin/jobs/{id}/edit-plan`.
5. ExtendScript imports media, creates sequence, places subclips and markers (single undo group).

**Note:** API must run on the same machine as Premiere (or have access to the same filesystem paths). Docker API cannot read host paths unless volumes are mounted.

---

### Phase 15: Turnkey clip — stitched render — **Implemented**

- **`app/services/video_renderer.py`** (`VideoRenderer`): cuts each edit-plan clip with FFmpeg (libx264/aac, uniform timescale/SAR), then concatenates via the FFmpeg concat demuxer into one `neurocut_render.mp4`.
- **`export_mode="render"`**: new pipeline branch (stage `rendering_clip`) that completes after producing the stitched MP4.
- **Routes**: `POST /jobs/generate` accepts `render`; standalone `POST /jobs/{id}/export/render` + `GET /jobs/{id}/export/render/download`.
- **Config**: `render_crf`, `render_preset`, `render_audio_bitrate`.
- **UI**: Turnkey clip task → inline video preview + one-click MP4 download.

### Phase 16 & 17: Subtitles with approval step — **Implemented**

- **Phase 16 (approval):** the subtitle task first runs transcribe-only, then the UI shows an editable transcript (`SubtitleEditor`) — user edits/removes lines and confirms before anything is rendered.
- **Phase 17 (burn-in):** `app/services/subtitle_burner.py` (`SubtitleBurner`) writes an SRT from the approved segments and burns it onto the original video with FFmpeg `subtitles` filter (`force_style` via libass). Runs inside the job dir to sidestep libass path-escaping issues; falls back from `-c:a copy` to AAC if needed.
- **Progress:** `app/services/subtitle_progress.py` (`SubtitleProgressTracker`) with atomic writes.
- **Routes**: `POST /jobs/{id}/subtitles/render` (approved segments + optional style), `GET /jobs/{id}/subtitles/status`, `GET /jobs/{id}/subtitles/download`.
- **Config**: `subtitle_font_size`, `subtitle_primary_color`, `subtitle_outline_color`, `subtitle_outline`, `subtitle_margin_v`, `subtitle_crf`, `subtitle_preset`.
- **UI**: Subtitles task → transcribe → approve/edit → burn (progress) → subtitled video preview + download.

**Reliability fix (shared):** all progress trackers now use `app/utils/progress_store.py` (atomic temp-file writes + resilient JSON reads) to eliminate the `/status` polling race that caused `JSONDecodeError`.

---

## Commit History

| Phase | Commit | Message | Branch |
| --- | --- | --- | --- |
| Phase 1 (setup, media_processor) | `83bcfad` | Initial commit | main |
| Phase 2 (transcriber) | `7e4ed44` | stage 2 | main |
| Phase 3 (ai_analyzer) | `0f0ce5a` | Stage 3 | main |
| Phase 4 (xml_generator, FCP7) | `7732512` | stage 4 | main |
| Phase 5 (pipeline + Streamlit) | `7df28cc` | stage 5 | main |
| Phase 6 (CapCut) | `93654be` | Add crappy capcut | `capcut` (not merged) |
| Phase 7 (clips ZIP) | `41b9a4c` | Add zip cutting | macport |
| Phase 8 (visual / silent video) | `d9e9356` | Fix cutting | macport |
| Phase 9 (model cascade + timecodes) | `1b42d48` | Fix request format | macport |
| Phase 10 (Docker, README) | `983e28a` | dockerisation and macportation | macport |
| Phase 11 (portable XML paths) | `c529ea9` | Add path fixing for xml | macport |
| Phase 12 (STT as standalone service) | *TBD* | *TBD* | macport |
| Phase 13 (Silero + GigaAM STT) | *TBD* | *TBD* | macport |
| Phase 14 (Premiere Plugin) | *TBD* | *TBD* | *TBD* |
| Phase 15 (turnkey stitched render) | *TBD* | *TBD* | *TBD* |
| Phase 16–17 (subtitles + approval) | *TBD* | *TBD* | *TBD* |