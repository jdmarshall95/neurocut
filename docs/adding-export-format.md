# How to add a new export format

Exports are selected via `export_mode` on `POST /jobs/generate` and handled in `PipelineRunner` (`app/services/pipeline.py`).

## Checklist

1. **Define mode** — extend `ExportMode` in `pipeline_progress.py` (and API schemas / frontend `ExportMode`).
2. **Implement exporter** — new service in `app/services/` that reads `edit_plan.json` (+ video path / sources manifest).
3. **Wire pipeline** — new stage + `progress.complete(...)` fields (paths for download).
4. **API** — ensure `/jobs/{id}/result` and download routes expose the artifact.
5. **UI** — task card + download button in `frontend/`.
6. **Docs** — README feature bullet + this file’s example table.

## Existing patterns

| Mode | Service | Artifact |
|------|---------|----------|
| `xml` | `xml_generator.py` | FCP7 XML |
| `clips` | `clip_exporter.py` | per-clip MP4 + ZIP |
| `render` | `video_renderer.py` | stitched MP4 |
| subtitles | `subtitle_burner.py` | burned MP4 |

## Multi-source jobs

Use `app/utils/sources_manifest.py` → `resolve_clip_times()` so cuts map from the **global** assembly timeline back to the correct source file.

## Suggested next formats

- FCPXML / Premiere markers JSON
- CMX3600 EDL
- Resolve `.drp` helpers (document limitations carefully)
