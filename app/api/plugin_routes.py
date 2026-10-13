import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.plugin_schemas import (
    PluginEditPlanResponse,
    PluginGenerateRequest,
    PluginGenerateResponse,
    PluginHealthResponse,
    PluginStatusResponse,
    TimelineClipResponse,
    TimelineMarkerResponse,
)
from app.api.routes import pipeline_status
from app.core.config import get_settings
from app.models.edit_plan import EditPlan
from app.services.pipeline import run_pipeline_job
from app.services.pipeline_progress import PipelineProgressTracker
from app.services.plugin_media import (
    PluginMediaError,
    prepare_job_media,
    resolve_plugin_media_path,
    validate_local_media_path,
)
from app.services.xml_generator import XMLGenerator
from app.utils.timeline_layout import build_timeline_clips, build_timeline_markers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugin", tags=["plugin"])


@router.get("/health", response_model=PluginHealthResponse)
async def plugin_health() -> PluginHealthResponse:
    settings = get_settings()
    return PluginHealthResponse(
        status="ok",
        plugin_enabled=settings.plugin_enabled,
        allow_any_local_path=settings.plugin_allow_any_local_path,
        allowed_roots=[str(path) for path in settings.resolved_plugin_allowed_roots],
        copy_media_to_storage=settings.plugin_copy_media_to_storage,
    )


@router.post("/jobs/generate", response_model=PluginGenerateResponse, status_code=202)
async def plugin_generate_job(
    request: PluginGenerateRequest,
    background_tasks: BackgroundTasks,
) -> PluginGenerateResponse:
    settings = get_settings()
    if not settings.plugin_enabled:
        raise HTTPException(status_code=403, detail="Plugin API is disabled.")

    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    try:
        local_path = validate_local_media_path(request.local_path, settings)
    except PluginMediaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = uuid4().hex
    settings.ensure_storage()

    try:
        media_path = prepare_job_media(local_path, job_id, settings)
    except PluginMediaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    reference_source = not settings.plugin_copy_media_to_storage
    PipelineProgressTracker(settings).start(
        job_id,
        prompt=prompt,
        export_mode="plugin",
    )
    background_tasks.add_task(
        run_pipeline_job,
        job_id,
        prompt,
        media_path,
        settings,
        export_mode="plugin",
        reference_source=reference_source,
    )
    logger.info(
        "[plugin] job=%s queued path=%s reference=%s",
        job_id,
        local_path,
        reference_source,
    )
    return PluginGenerateResponse(
        job_id=job_id,
        status="started",
        media_path=str(local_path),
    )


@router.get("/jobs/{job_id}/status", response_model=PluginStatusResponse)
async def plugin_job_status(job_id: str) -> PluginStatusResponse:
    status = await pipeline_status(job_id)
    return PluginStatusResponse(
        pipeline=status.pipeline,
        transcription=status.transcription,
        analysis=status.analysis,
    )


@router.get("/jobs/{job_id}/edit-plan", response_model=PluginEditPlanResponse)
async def plugin_edit_plan(job_id: str) -> PluginEditPlanResponse:
    settings = get_settings()
    pipeline = PipelineProgressTracker(settings).read(job_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if pipeline.stage == "failed":
        raise HTTPException(status_code=422, detail=pipeline.error or "Pipeline failed.")
    if pipeline.stage != "completed":
        raise HTTPException(
            status_code=404,
            detail=f"Edit plan not ready for job '{job_id}'.",
        )

    job_dir = settings.storage_path / job_id
    edit_plan_path = job_dir / "edit_plan.json"
    if not edit_plan_path.is_file():
        raise HTTPException(status_code=404, detail=f"Edit plan missing for job '{job_id}'.")

    plan = EditPlan.model_validate_json(edit_plan_path.read_text(encoding="utf-8"))

    try:
        media_path = resolve_plugin_media_path(job_dir)
    except PluginMediaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    fps = pipeline.fps
    if fps is None:
        metadata = XMLGenerator(settings)._probe_video(media_path)
        fps = metadata.fps or settings.default_fps

    timebase = pipeline.timebase or int(round(fps))
    timeline_clips = [
        TimelineClipResponse(**clip.__dict__)
        for clip in build_timeline_clips(plan, fps)
    ]
    timeline_markers = [
        TimelineMarkerResponse(**marker.__dict__)
        for marker in build_timeline_markers(plan.markers, fps)
    ]

    return PluginEditPlanResponse(
        job_id=job_id,
        prompt=pipeline.prompt or "",
        media_path=str(media_path),
        original_filename=media_path.name,
        fps=fps,
        timebase=timebase,
        clip_count=len(plan.clips),
        marker_count=len(plan.markers),
        analysis_mode=pipeline.analysis_mode,
        edit_plan=plan,
        timeline_clips=timeline_clips,
        timeline_markers=timeline_markers,
    )
