
from pydantic import BaseModel, Field

from app.models.edit_plan import EditPlan
from app.models.visual_timeline import TimelineSource
from app.services.analysis_progress import AnalysisProgressState
from app.services.pipeline_progress import ExportMode, PipelineProgressState
from app.services.transcription_progress import TranscriptionProgressState


class HealthResponse(BaseModel):
    status: str
    app_name: str


class TranscriptSegmentResponse(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class MediaProcessingResponse(BaseModel):
    job_id: str
    original_path: str
    audio_path: str | None = None
    proxy_video_path: str
    has_audio: bool = True
    duration_sec: float | None = None


class TranscriptionStartResponse(BaseModel):
    job_id: str
    status: str


class TranscribeJobStartResponse(BaseModel):
    job_id: str
    status: str
    task: str = "transcribe"


class TranscriptionResultResponse(BaseModel):
    job_id: str
    transcript_path: str
    language: str | None = None
    duration: float | None = None
    elapsed_sec: float | None = None
    device: str | None = None
    compute_type: str | None = None
    segment_count: int
    transcript: list[TranscriptSegmentResponse]


class TranscriptResponse(BaseModel):
    job_id: str | None = None
    source: str = "speech"
    has_speech: bool = True
    file_hash: str | None = None
    cached: bool = False
    language: str | None = None
    duration: float | None = None
    segment_count: int
    transcript: list[TranscriptSegmentResponse]


class TranscriptUploadResponse(BaseModel):
    job_id: str | None = None
    file_hash: str | None = None
    segment_count: int
    duration: float | None = None
    transcript_path: str | None = None
    cache_path: str | None = None
    transcript: list[TranscriptSegmentResponse]


class AnalyzeRequest(BaseModel):
    prompt: str = Field(min_length=1)


class AnalysisStartResponse(BaseModel):
    job_id: str
    status: str


class AnalysisResultResponse(BaseModel):
    job_id: str
    edit_plan_path: str
    clips_count: int
    markers_count: int
    elapsed_sec: float | None = None
    model: str | None = None
    edit_plan: EditPlan


class XMLExportResponse(BaseModel):
    job_id: str
    xml_path: str
    clip_count: int
    marker_count: int
    sequence_duration_frames: int
    fps: float
    timebase: int


class ClipExportResponse(BaseModel):
    job_id: str
    clips_dir: str
    zip_path: str
    manifest_path: str
    clip_count: int
    marker_count: int


class RenderExportResponse(BaseModel):
    job_id: str
    render_path: str
    clip_count: int
    duration_sec: float


class SubtitleSegmentInput(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class SubtitleStyleInput(BaseModel):
    font_size: int | None = Field(default=None, ge=8, le=120)
    primary_color: str | None = None
    outline_color: str | None = None
    outline: int | None = Field(default=None, ge=0, le=10)
    margin_v: int | None = Field(default=None, ge=0, le=400)
    font_name: str | None = None
    border_style: int | None = Field(default=None)


class SubtitleFont(BaseModel):
    name: str
    label: str


class SubtitleFontsResponse(BaseModel):
    fonts: list[SubtitleFont]


class SubtitleProofreadRequest(BaseModel):
    segments: list[SubtitleSegmentInput] = Field(min_length=1)
    language: str | None = None


class SubtitleProofreadResponse(BaseModel):
    segments: list[TranscriptSegmentResponse]
    changed: bool


class SubtitleRenderRequest(BaseModel):
    segments: list[SubtitleSegmentInput] = Field(min_length=1)
    style: SubtitleStyleInput | None = None
    auto_chunk: bool | None = None
    max_words: int | None = Field(default=None, ge=1, le=5)


class SubtitleRenderStartResponse(BaseModel):
    job_id: str
    status: str
    segment_count: int


class SubtitleChunkRequest(BaseModel):
    segments: list[SubtitleSegmentInput] = Field(min_length=1)
    max_words: int | None = Field(default=None, ge=1, le=5)


class SubtitleChunkSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    overflow: bool = False


class SubtitleChunkResponse(BaseModel):
    job_id: str
    frame_width: int
    font_size: int
    char_budget: int
    segment_count: int
    overflow_count: int
    segments: list[SubtitleChunkSegment]


class SceneDetectionResponse(BaseModel):
    job_id: str
    timeline_path: str
    shot_count: int
    duration: float | None = None
    scene_threshold: float


class GenerateStartResponse(BaseModel):
    job_id: str
    status: str
    export_mode: ExportMode


class PipelineStatusResponse(BaseModel):
    pipeline: PipelineProgressState
    transcription: TranscriptionProgressState | None = None
    analysis: AnalysisProgressState | None = None


class JobResultResponse(BaseModel):
    job_id: str
    prompt: str
    export_mode: ExportMode = "xml"
    analysis_mode: TimelineSource | None = None
    original_path: str
    transcript_path: str
    visual_timeline_path: str | None = None
    edit_plan_path: str
    xml_path: str | None = None
    clips_dir_path: str | None = None
    clips_zip_path: str | None = None
    render_path: str | None = None
    language: str | None = None
    duration: float | None = None
    clip_count: int
    marker_count: int
    fps: float | None = None
    timebase: int | None = None
    edit_plan: EditPlan
    transcript: list[TranscriptSegmentResponse]
