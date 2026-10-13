# Project: NeuroCut MVP (AI Video Editor Assistant)

## 1. Project Overview
We are building an MVP for an AI video editing assistant. 
**User Flow:** User uploads a video file + text prompt (Technical Specification/Task). 
**System Flow:** Backend extracts audio, transcribes it with timestamps, sends video/audio context + prompt to an LLM. LLM returns a structured JSON of selected clips and markers. Backend converts this JSON into an FCP7 XML (compatible with Premiere Pro and DaVinci Resolve) and returns it to the user.
**Goal:** Provide a rough cut in a format readable by professional NLEs (Non-Linear Editors).

## 2. Tech Stack (Strict)
- **Language:** Python 3.11+
- **Backend API:** FastAPI
- **Frontend (MVP):** React (Vite) + Tailwind + Headless UI
- **Audio Transcription:** `faster-whisper` (must use `word_timestamps=True` or segment level)
- **Video Processing:** `ffmpeg-python` (for downscaling and audio extraction)
- **LLM:** Google Gemini API (`google-genai` or `langchain`). *Reason: Best multimodal context and long context window.*
- **XML Generation:** `Jinja2` (Templating engine for FCP7 XML).
- **Async Tasks:** FastAPI `BackgroundTasks` (for MVP simplicity).

## 3. Architecture & Data Flow
1. **Ingest:** Receive video + prompt.
2. **Prep:** FFmpeg extracts audio (`.wav`) and creates a low-res proxy video (`.mp4`, 480p) for LLM vision.
3. **Transcribe:** `faster-whisper` generates a transcript with exact start/end timestamps.
4. **Analyze:** LLM receives: Prompt, Transcript (with timestamps), and Proxy Video. LLM outputs a strict JSON.
5. **Export:** Python script parses JSON, injects data into FCP7 XML Jinja2 template, saves `.xml`.
6. **Return:** API returns download links for the `.xml` file.
## Strict Rules for Cursor AI
1. **No Placeholders:** Do not write `# TODO: implement this`. Write the actual working code.
2. **Error Handling:** Wrap FFmpeg and Whisper calls in try/except blocks. If LLM returns invalid JSON, implement a retry mechanism with a correction prompt.
3. **Type Hinting:** Use Python type hints everywhere. Use Pydantic models for all data structures.
4. **Environment:** Assume API keys are in `.env`. Use `pydantic-settings` to load them.
5. **File Paths:** When generating the XML, the `<pathurl>` for the media must point to the original uploaded video file. Use absolute paths or handle relative paths correctly so the NLE can relink if needed.
6. **FCP7 XML specifics:** Ensure `<rate>` (framerate) is correctly defined in the XML header, otherwise Premiere will import the clips at the wrong speed. Default to 30fps for MVP unless detected otherwise.

