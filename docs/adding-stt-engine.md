# How to add a new STT engine

NeuroCut routes speech recognition through `STTService` (`app/services/stt_service.py`) based on `STT_ENGINE`.

## Checklist

1. **Implement** a module under `app/services/`, e.g. `transcriber_myengine.py`, returning segments with `start`, `end`, `text`.
2. **Register** the engine name in:
   - `Settings.stt_engine` validator (`app/core/config.py`)
   - `STTService` selection logic
3. **Dependencies** — if heavy, add `requirements-myengine.txt` and a Docker `ARG INSTALL_MYENGINE=0` like Silero/GigaAM.
4. **Config** — document env vars in `.env.example`.
5. **Cache** — reuse file-hash transcript cache when possible (`STT_CACHE_ENABLED`).
6. **Test** — unit-test parsing; smoke-test a 10–30s clip.
7. **License** — note model license constraints in README / NOTICE.

## Contract

Downstream code expects `transcript.json` with:

```json
{
  "source": "speech",
  "has_speech": true,
  "language": "ru",
  "duration": 42.0,
  "segments": [{ "start": 0.0, "end": 1.2, "text": "..." }]
}
```

Keep timestamps in **seconds** (float).

## Tips

- Prefer CPU-friendly defaults for Docker users.
- Document language coverage honestly (which locales each engine supports).
- For `auto` mode, define clear language → engine rules.
