from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.utils.progress_store import atomic_write_text, read_json_resilient

TranscriptionStatus = Literal[
    "idle",
    "queued",
    "loading_model",
    "transcribing",
    "completed",
    "failed",
]


class TranscriptionProgressState(BaseModel):
    job_id: str
    status: TranscriptionStatus = "idle"
    segment_count: int = 0
    progress_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    audio_duration_sec: float | None = None
    processed_until_sec: float = 0.0
    elapsed_sec: float = 0.0
    model: str | None = None
    device: str | None = None
    compute_type: str | None = None
    message: str = ""
    last_segment_preview: str | None = None
    error: str | None = None
    updated_at: str = ""


class TranscriptionProgressTracker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _progress_path(self, job_id: str) -> Path:
        return self.settings.storage_path / job_id / "transcription_progress.json"

    def read(self, job_id: str) -> TranscriptionProgressState | None:
        data = read_json_resilient(self._progress_path(job_id))
        if data is None:
            return None
        return TranscriptionProgressState.model_validate(data)

    def write(self, state: TranscriptionProgressState) -> Path:
        state.updated_at = datetime.now(UTC).isoformat()
        path = self._progress_path(state.job_id)
        atomic_write_text(path, state.model_dump_json(indent=2))
        return path

    def queue(self, job_id: str, *, message: str = "Transcription queued...") -> TranscriptionProgressState:
        state = TranscriptionProgressState(
            job_id=job_id,
            status="queued",
            message=message,
        )
        self.write(state)
        return state

    def start(
        self,
        job_id: str,
        *,
        model: str,
        device: str,
        compute_type: str,
        message: str,
    ) -> TranscriptionProgressState:
        state = TranscriptionProgressState(
            job_id=job_id,
            status="loading_model",
            model=model,
            device=device,
            compute_type=compute_type,
            message=message,
        )
        self.write(state)
        return state

    def update(self, job_id: str, **fields: Any) -> TranscriptionProgressState:
        current = self.read(job_id)
        if current is None:
            current = TranscriptionProgressState(job_id=job_id)
        updated = current.model_copy(update=fields)
        self.write(updated)
        return updated

    def fail(self, job_id: str, error: str) -> TranscriptionProgressState:
        current = self.read(job_id)
        if current is None:
            current = TranscriptionProgressState(job_id=job_id)
        return self.update(
            job_id,
            status="failed",
            error=error,
            message=error,
            elapsed_sec=current.elapsed_sec,
        )
