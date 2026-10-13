# Contributing to NeuroCut

Thanks for helping improve NeuroCut — an open-source **AI video editing** assistant
(automatic cutting, Whisper transcription, FCP7 XML export).

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Ways to contribute

- Bug reports and reproducible issues
- Feature requests with a clear use case (editors, NLE plugins, STT, export)
- Pull requests (fixes, docs, tests, new STT engines, export formats)
- Demo assets, screenshots, translations

## Development setup

### Prerequisites

- Docker Desktop **or** Python 3.11+, Node.js 20+, FFmpeg on `PATH`
- A [Google Gemini API key](https://aistudio.google.com/apikey) (optional DeepSeek key)

### Fastest path (Docker)

```bash
git clone https://github.com/jdmarshall95/neurocut.git
cd neurocut
cp .env.example .env   # set GEMINI_API_KEY
docker compose up --build
```

- UI: http://localhost:8501  
- API + OpenAPI: http://localhost:8000/docs  

### Local API + UI

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install ruff pytest     # dev tools
cp .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm install
npm run dev                 # http://localhost:8501
```

Optional STT extras: `requirements-silero.txt`, `requirements-gigaam.txt`.

## Code style

| Area | Tool | Notes |
|------|------|--------|
| Python | **Ruff** | lint + format; target `app/` |
| Python types | prefer type hints on public APIs | |
| Frontend | TypeScript strict + Vite build | `npm run build` must pass |
| Frontend format | Prettier (optional locally) | match existing Tailwind style |

```bash
# Python
ruff check app
ruff format app

# Frontend
cd frontend && npm run build
```

Keep PRs focused. Prefer small, reviewable changes over large refactors.

## Commit messages (Conventional Commits)

```
feat: add EDL export format
fix: clamp scene cuts to source boundaries
docs: document GigaAM install
chore: tighten CI cache
test: cover sources_manifest resolve_global
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`.

## Pull request process

1. Open an issue first for large features (optional for tiny docs/fixes).
2. Branch from `main`:
   - `feat/<short-name>`
   - `fix/<short-name>`
   - `docs/<short-name>`
3. Make sure Docker still starts (`docker compose up --build`) for user-facing changes.
4. Fill the PR template: what / why / how tested.
5. One logical change per PR when possible.
6. Maintainers review; address feedback; squash or rebase as requested.

## Tests

The project is young — add tests next to what you change.

```bash
pip install pytest
pytest -q
```

Suggested coverage when touching:

- `app/utils/` — pure helpers (timestamps, sources_manifest)
- `app/services/scene_detector.py` — cut merging with fixtures
- Frontend — keep `tsc --noEmit` green via `npm run build`

Until a large suite exists, a **manual smoke test** is required for pipeline PRs:

1. `docker compose up --build`
2. Upload a short clip + simple brief (e.g. “cut 3–4s highlight moments”)
3. Confirm job completes and download works

## Adding a new STT engine

1. Implement a transcriber in `app/services/` (see `transcriber.py`, `transcriber_silero.py`, `transcriber_gigaam.py`).
2. Wire it in `app/services/stt_service.py` and `STT_ENGINE` in `app/core/config.py`.
3. Add optional `requirements-*.txt` + Docker build arg if heavy deps.
4. Document env vars in `.env.example` and `docs/adding-stt-engine.md`.
5. Note language coverage and license of the model.

## Adding a new export format

1. Add a service under `app/services/` (mirror `xml_generator.py` / `clip_exporter.py`).
2. Extend `ExportMode` / pipeline stages in `pipeline.py` + progress tracker.
3. Expose download in `app/api/routes.py` and frontend result UI.
4. Document in `docs/adding-export-format.md`.

## Premiere plugin

See [docs/plugin-development.md](docs/plugin-development.md) and `premiere/NeuroCut/`.

## Questions

Open a Discussion or Issue with the `question` label. For security issues, use [SECURITY.md](SECURITY.md).
