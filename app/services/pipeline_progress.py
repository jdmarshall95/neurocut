from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.models.visual_timeline import TimelineSource
from app.utils.progress_store import atomic_write_text, read_json_resilient

ExportMode = Literal["xml", "clips", "plugin", "render"]
PipelineStage = Literal[
    "queued",
    "extracting_audio",
    "transcribing",
    "analyzing_scenes",
    "ai_editing",
    "generating_xml",
    "generating_clips",
    "rendering_clip",
    "applying_timeline",
    "completed",
    "failed",
]

STAGE_MESSAGES: dict[PipelineStage, str] = {
    "queued": "Preparing to process...",
    "extracting_audio": "Extracting audio...",
    "transcribing": "Transcribing...",
    "analyzing_scenes": "Analyzing scenes...",
    "ai_editing": "AI is editing...",
    "generating_xml": "Generating XML...",
    "generating_clips": "Exporting clips...",
    "rendering_clip": "Rendering turnkey clip...",
    "applying_timeline": "Ready for Premiere...",
    "completed": "Done.",
    "failed": "Processing failed.",
}

STAGE_PROGRESS: dict[PipelineStage, float] = {
    "queued": 0.0,
    "extracting_audio": 10.0,
    "transcribing": 25.0,
    "analyzing_scenes": 45.0,
    "ai_editing": 60.0,
    "generating_xml": 90.0,
    "generating_clips": 90.0,
    "rendering_clip": 90.0,
    "applying_timeline": 95.0,
    "completed": 100.0,
    "failed": 0.0,
}


class PipelineProgressState(BaseModel):
    job_id: str
    stage: PipelineStage = "queued"
    message: str = STAGE_MESSAGES["queued"]
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    export_mode: ExportMode = "xml"
    analysis_mode: TimelineSource | None = None
    prompt: str | None = None
    error: str | None = None
    xml_path: str | None = None
    clips_dir_path: str | None = None
    clips_zip_path: str | None = None
    render_path: str | None = None
    edit_plan_path: str | None = None
    transcript_path: str | None = None
    visual_timeline_path: str | None = None
    original_path: str | None = None
    clip_count: int = 0
    marker_count: int = 0
    fps: float | None = None
    timebase: int | None = None
    updated_at: str = ""


class PipelineProgressTracker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _progress_path(self, job_id: str) -> Path:
        return self.settings.storage_path / job_id / "pipeline_progress.json"

    def read(self, job_id: str) -> PipelineProgressState | None:
        data = read_json_resilient(self._progress_path(job_id))
        if data is None:
            return None
        return PipelineProgressState.model_validate(data)

    def write(self, state: PipelineProgressState) -> Path:
        state.updated_at = datetime.now(UTC).isoformat()
        path = self._progress_path(state.job_id)
        atomic_write_text(path, state.model_dump_json(indent=2))
        return path

    def start(self, job_id: str, *, prompt: str, export_mode: ExportMode = "xml") -> PipelineProgressState:
        state = PipelineProgressState(
            job_id=job_id,
            stage="queued",
            message=STAGE_MESSAGES["queued"],
            progress_percent=STAGE_PROGRESS["queued"],
            prompt=prompt,
            export_mode=export_mode,
        )
        self.write(state)
        return state

    def set_stage(
        self,
        job_id: str,
        stage: PipelineStage,
        *,
        message: str | None = None,
        progress_percent: float | None = None,
        **fields: Any,
    ) -> PipelineProgressState:
        current = self.read(job_id) or PipelineProgressState(job_id=job_id)
        updated = current.model_copy(
            update={
                "stage": stage,
                "message": message or STAGE_MESSAGES[stage],
                "progress_percent": (
                    progress_percent
                    if progress_percent is not None
                    else STAGE_PROGRESS.get(stage, current.progress_percent)
                ),
                **fields,
            }
        )
        self.write(updated)
        return updated

    def fail(self, job_id: str, error: str) -> PipelineProgressState:
        current = self.read(job_id) or PipelineProgressState(job_id=job_id)
        return self.set_stage(
            job_id,
            "failed",
            message=error,
            error=error,
            progress_percent=current.progress_percent,
            prompt=current.prompt,
        )

    def complete(self, job_id: str, **fields: Any) -> PipelineProgressState:
        return self.set_stage(job_id, "completed", progress_percent=100.0, **fields)
