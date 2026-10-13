from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.utils.progress_store import atomic_write_text, read_json_resilient

SubtitleStatus = Literal[
    "idle",
    "queued",
    "burning",
    "completed",
    "failed",
]


class SubtitleProgressState(BaseModel):
    job_id: str
    status: SubtitleStatus = "idle"
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    message: str = ""
    segment_count: int = 0
    output_path: str | None = None
    error: str | None = None
    updated_at: str = ""


class SubtitleProgressTracker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _progress_path(self, job_id: str) -> Path:
        return self.settings.storage_path / job_id / "subtitle_progress.json"

    def read(self, job_id: str) -> SubtitleProgressState | None:
        data = read_json_resilient(self._progress_path(job_id))
        if data is None:
            return None
        return SubtitleProgressState.model_validate(data)

    def write(self, state: SubtitleProgressState) -> Path:
        state.updated_at = datetime.now(UTC).isoformat()
        path = self._progress_path(state.job_id)
        atomic_write_text(path, state.model_dump_json(indent=2))
        return path

    def queue(self, job_id: str, *, segment_count: int) -> SubtitleProgressState:
        state = SubtitleProgressState(
            job_id=job_id,
            status="queued",
            segment_count=segment_count,
            message="Subtitle burn-in queued...",
        )
        self.write(state)
        return state

    def update(self, job_id: str, **fields: Any) -> SubtitleProgressState:
        current = self.read(job_id) or SubtitleProgressState(job_id=job_id)
        updated = current.model_copy(update=fields)
        self.write(updated)
        return updated

    def fail(self, job_id: str, error: str) -> SubtitleProgressState:
        current = self.read(job_id) or SubtitleProgressState(job_id=job_id)
        return self.update(
            job_id,
            status="failed",
            error=error,
            message=error,
            segment_count=current.segment_count,
        )
