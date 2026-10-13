# Premiere Pro plugin development

Location: `premiere/NeuroCut/` (Adobe CEP panel).

## What it does

1. User selects a **local media path** in Premiere.
2. Panel calls NeuroCut API (`/plugin/jobs/generate`) with path + prompt.
3. Polls `/plugin/jobs/{id}/status`.
4. Fetches `/plugin/jobs/{id}/edit-plan` and applies clips/markers via ExtendScript.

No large file upload — the API must be able to **read the same path** (Docker mount or local uvicorn).

## Install / debug

```bash
./scripts/install_premiere_plugin.sh
```

Enable PlayerDebugMode for unsigned extensions (script prints steps).  
Open **Window → Extensions → NeuroCut**.

## Docker + host paths (macOS)

```bash
export PLUGIN_MEDIA_ROOT="$HOME/Movies"
docker compose -f docker-compose.yml -f docker-compose.plugin.yml up --build -d api
```

Media must live under `PLUGIN_MEDIA_ROOT`. Prefer `PLUGIN_ALLOWED_ROOTS` over `PLUGIN_ALLOW_ANY_LOCAL_PATH` outside local dev.

## Dev tips

- Keep CEP JS thin; business logic stays in FastAPI.
- Version the panel `CSXS/manifest.xml` when changing APIs.
- Test with short clips first — STT + LLM can be slow on CPU.
- CORS: `PLUGIN_CORS_ALLOW_ALL=true` is convenient for CEP; tighten for shared deployments.

## Related API

| Method | Path |
|--------|------|
| GET | `/plugin/health` |
| POST | `/plugin/jobs/generate` |
| GET | `/plugin/jobs/{id}/status` |
| GET | `/plugin/jobs/{id}/edit-plan` |
