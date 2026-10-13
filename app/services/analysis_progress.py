from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.utils.progress_store import atomic_write_text, read_json_resilient

AnalysisStatus = Literal[
    "idle",
    "queued",
    "uploading_video",
    "waiting_video",
    "analyzing",
    "completed",
    "failed",
]


class AnalysisProgressState(BaseModel):
    job_id: str
    status: AnalysisStatus = "idle"
    attempt: int = 0
    max_attempts: int = 3
    elapsed_sec: float = 0.0
    model: str | None = None
    message: str = ""
    clips_count: int = 0
    markers_count: int = 0
    error: str | None = None
    updated_at: str = ""


class AnalysisProgressTracker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _progress_path(self, job_id: str) -> Path:
        return self.settings.storage_path / job_id / "analysis_progress.json"

    def read(self, job_id: str) -> AnalysisProgressState | None:
        data = read_json_resilient(self._progress_path(job_id))
        if data is None:
            return None
        return AnalysisProgressState.model_validate(data)

    def write(self, state: AnalysisProgressState) -> Path:
        state.updated_at = datetime.now(UTC).isoformat()
        path = self._progress_path(state.job_id)
        atomic_write_text(path, state.model_dump_json(indent=2))
        return path

    def queue(self, job_id: str, *, max_attempts: int, model: str) -> AnalysisProgressState:
        state = AnalysisProgressState(
            job_id=job_id,
            status="queued",
            max_attempts=max_attempts,
            model=model,
            message="AI analysis queued...",
        )
        self.write(state)
        return state

    def update(self, job_id: str, **fields: Any) -> AnalysisProgressState:
        current = self.read(job_id)
        if current is None:
            current = AnalysisProgressState(job_id=job_id)
        updated = current.model_copy(update=fields)
        self.write(updated)
        return updated

    def fail(self, job_id: str, error: str) -> AnalysisProgressState:
        current = self.read(job_id)
        if current is None:
            current = AnalysisProgressState(job_id=job_id)
        return self.update(
            job_id,
            status="failed",
            error=error,
            message=error,
            elapsed_sec=current.elapsed_sec,
            attempt=current.attempt,
            max_attempts=current.max_attempts,
            model=current.model,
        )
