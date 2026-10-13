from pydantic import BaseModel, Field

from app.models.edit_plan import EditPlan
from app.services.analysis_progress import AnalysisProgressState
from app.services.pipeline_progress import PipelineProgressState
from app.services.transcription_progress import TranscriptionProgressState


class PluginHealthResponse(BaseModel):
    status: str
    plugin_enabled: bool
    allow_any_local_path: bool
    allowed_roots: list[str]
    copy_media_to_storage: bool


class PluginGenerateRequest(BaseModel):
    local_path: str = Field(min_length=1)
    prompt: str = Field(min_length=1)


class PluginGenerateResponse(BaseModel):
    job_id: str
    status: str
    export_mode: str = "plugin"
    media_path: str


class PluginStatusResponse(BaseModel):
    pipeline: PipelineProgressState
    transcription: TranscriptionProgressState | None = None
    analysis: AnalysisProgressState | None = None


class TimelineClipResponse(BaseModel):
    id: str
    name: str
    track: int
    source_start_sec: float
    source_end_sec: float
    timeline_start_sec: float
    timeline_end_sec: float
    reason: str


class TimelineMarkerResponse(BaseModel):
    name: str
    comment: str
    time_sec: float
    frame: int


class PluginEditPlanResponse(BaseModel):
    job_id: str
    prompt: str
    media_path: str
    original_filename: str
    fps: float
    timebase: int
    clip_count: int
    marker_count: int
    analysis_mode: str | None = None
    edit_plan: EditPlan
    timeline_clips: list[TimelineClipResponse]
    timeline_markers: list[TimelineMarkerResponse]
