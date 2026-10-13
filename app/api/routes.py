import json
import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.schemas import (
    AnalysisResultResponse,
    AnalysisStartResponse,
    AnalyzeRequest,
    ClipExportResponse,
    GenerateStartResponse,
    HealthResponse,
    JobResultResponse,
    MediaProcessingResponse,
    PipelineStatusResponse,
    RenderExportResponse,
    SceneDetectionResponse,
    SubtitleChunkRequest,
    SubtitleChunkResponse,
    SubtitleChunkSegment,
    SubtitleFont,
    SubtitleFontsResponse,
    SubtitleProofreadRequest,
    SubtitleProofreadResponse,
    SubtitleRenderRequest,
    SubtitleRenderStartResponse,
    TranscribeJobStartResponse,
    TranscriptionResultResponse,
    TranscriptionStartResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
    TranscriptUploadResponse,
    XMLExportResponse,
)
from app.core.config import Settings, get_settings
from app.models.edit_plan import EditPlan
from app.utils.media_path import save_source_media
from app.services.ai_analyzer import AIAnalysisError, AIAnalyzer
from app.services.analysis_progress import AnalysisProgressTracker
from app.services.clip_exporter import ClipExportError, ClipExporter
from app.services.media_processor import MediaProcessingError, MediaProcessor
from app.services.pipeline import run_pipeline_job
from app.services.pipeline_progress import ExportMode, PipelineProgressTracker
from app.services.scene_detector import SceneDetectionError, SceneDetector
from app.services.stt_service import STTOptions, STTService, STTServiceError
from app.services.subtitle_burner import (
    SubtitleBurnError,
    SubtitleBurner,
    SubtitleSegment,
    SubtitleStyle,
    available_fonts,
)
from app.services.subtitle_progress import SubtitleProgressTracker
from app.services.text_proofreader import ProofreadError, TextProofreader
from app.services.transcriber import TranscriptionError, Transcriber
from app.services.transcription_progress import TranscriptionProgressTracker
from app.services.video_renderer import VideoRenderError, VideoRenderer
from app.services.xml_generator import XMLGenerationError, XMLGenerator

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_transcription_job(job_id: str, settings: Settings) -> None:
    job_dir = settings.storage_path / job_id
    audio_path = job_dir / "audio.wav"
    transcript_path = job_dir / "transcript.json"

    # Phase 12: respect user-supplied transcripts when the flag is enabled.
    if (
        settings.skip_stt_if_transcript_provided
        and transcript_path.is_file()
        and _transcript_is_uploaded(transcript_path)
    ):
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        segments = payload.get("segments", [])
        TranscriptionProgressTracker(settings).update(
            job_id,
            status="completed",
            segment_count=len(segments),
            progress_percent=100.0,
            message=f"Done: using uploaded transcript ({len(segments)} segments)",
        )
        return

    stt_service = STTService(settings)
    transcriber = Transcriber(settings)
    try:
        if audio_path.is_file():
            stt_service.transcribe(audio_path, STTOptions(), job_id=job_id)
            return

        original_candidates = sorted(
            path
            for path in job_dir.glob("original.*")
            if path.is_file()
        )
        if not original_candidates:
            TranscriptionProgressTracker(settings).fail(
                job_id,
                f"Audio file not found for job '{job_id}'.",
            )
            return

        processor = MediaProcessor(settings)
        has_audio, duration = processor._probe_media(original_candidates[0])
        if has_audio:
            TranscriptionProgressTracker(settings).fail(
                job_id,
                f"Audio file not found for job '{job_id}'. Run media processing first.",
            )
            return

        transcriber.record_no_audio(job_id=job_id, duration=duration or None, save=True)
    except (TranscriptionError, STTServiceError) as exc:
        logger.exception("[transcribe] job=%s failed: %s", job_id, exc)
        TranscriptionProgressTracker(settings).fail(job_id, str(exc))
    except Exception as exc:
        logger.exception("[transcribe] job=%s unexpected error", job_id)
        TranscriptionProgressTracker(settings).fail(job_id, str(exc))


def _transcript_is_uploaded(transcript_path: Path) -> bool:
    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return payload.get("source") == "uploaded"


def _run_transcribe_only_job(job_id: str, upload_path: Path, settings: Settings) -> None:
    """Upload → extract audio → transcribe (no LLM, no proxy). Phase 12 UX."""
    tracker = TranscriptionProgressTracker(settings)
    try:
        tracker.update(
            job_id,
            status="loading_model",
            model=settings.whisper_model,
            device="pending",
            compute_type="pending",
            message="Extracting audio track...",
        )
        processor = MediaProcessor(settings)
        has_audio, duration = processor._probe_media(upload_path)
        if not has_audio:
            Transcriber(settings).record_no_audio(
                job_id=job_id,
                duration=duration or None,
                save=True,
            )
            return

        audio_path = processor.extract_audio(
            upload_path,
            job_id=job_id,
            has_audio=True,
            duration_sec=duration,
        )
        if audio_path is None:
            Transcriber(settings).record_no_audio(
                job_id=job_id,
                duration=duration or None,
                save=True,
            )
            return

        STTService(settings).transcribe(audio_path, STTOptions(), job_id=job_id)
    except (MediaProcessingError, TranscriptionError, STTServiceError) as exc:
        logger.exception("[transcribe-only] job=%s failed: %s", job_id, exc)
        tracker.fail(job_id, str(exc))
    except Exception as exc:
        logger.exception("[transcribe-only] job=%s unexpected error", job_id)
        tracker.fail(job_id, str(exc))


def _run_analysis_job(job_id: str, prompt: str, settings: Settings) -> None:
    analyzer = AIAnalyzer(settings)
    try:
        analyzer.analyze(job_id, prompt, save=True)
    except AIAnalysisError as exc:
        logger.exception("[analyze] job=%s failed: %s", job_id, exc)
        AnalysisProgressTracker(settings).fail(job_id, str(exc))
    except Exception as exc:
        logger.exception("[analyze] job=%s unexpected error", job_id)
        AnalysisProgressTracker(settings).fail(job_id, str(exc))


def _run_subtitle_job(
    job_id: str,
    segments: list[SubtitleSegment],
    style: SubtitleStyle | None,
    settings: Settings,
    *,
    auto_chunk: bool | None = None,
    max_words: int | None = None,
) -> None:
    tracker = SubtitleProgressTracker(settings)
    try:
        tracker.update(
            job_id,
            status="burning",
            progress_percent=20.0,
            message="Burning subtitles into video...",
        )
        result = SubtitleBurner(settings).burn(
            job_id,
            segments,
            style=style,
            auto_chunk=auto_chunk,
            max_words=max_words,
        )
        tracker.update(
            job_id,
            status="completed",
            progress_percent=100.0,
            message="Done: subtitles burned into video.",
            output_path=str(result.output_path),
            segment_count=result.segment_count,
        )
    except SubtitleBurnError as exc:
        logger.exception("[subtitles] job=%s failed: %s", job_id, exc)
        tracker.fail(job_id, str(exc))
    except Exception as exc:
        logger.exception("[subtitles] job=%s unexpected error", job_id)
        tracker.fail(job_id, str(exc))


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", app_name=settings.app_name)


@router.post("/jobs/generate", response_model=GenerateStartResponse, status_code=202)
async def generate_job(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    prompt: str = Form(...),
    export_mode: ExportMode = Form(default="xml"),
) -> GenerateStartResponse:
    settings = get_settings()
    if not files:
        raise HTTPException(status_code=400, detail="At least one video file is required.")
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")
    if export_mode not in {"xml", "clips", "render"}:
        raise HTTPException(
            status_code=400,
            detail="export_mode must be 'xml', 'clips' or 'render'.",
        )

    job_id = uuid4().hex
    job_dir = settings.ensure_storage() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    upload_paths: list[Path] = []
    original_names: list[str] = []

    for index, file in enumerate(files, start=1):
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded file #{index} must have a filename.",
            )
        suffix = Path(file.filename).suffix or ".mp4"
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded file '{file.filename}' is empty.",
            )
        if len(files) == 1:
            upload_path = job_dir / f"original{suffix}"
        else:
            upload_path = job_dir / "sources" / f"source_{index:03d}{suffix}"
            upload_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(content)
        upload_paths.append(upload_path)
        original_names.append(file.filename)

    if len(upload_paths) == 1:
        save_source_media(
            job_dir,
            original_filename=original_names[0],
            stored_filename=upload_paths[0].name,
        )
    else:
        save_source_media(
            job_dir,
            original_filename=", ".join(original_names),
            stored_filename="proxy_480p.mp4",
        )

    PipelineProgressTracker(settings).start(
        job_id,
        prompt=prompt.strip(),
        export_mode=export_mode,
    )
    background_tasks.add_task(
        run_pipeline_job,
        job_id,
        prompt.strip(),
        upload_paths if len(upload_paths) > 1 else upload_paths[0],
        settings,
        export_mode=export_mode,
    )
    logger.info(
        "[pipeline] job=%s queued export_mode=%s sources=%d",
        job_id,
        export_mode,
        len(upload_paths),
    )
    return GenerateStartResponse(job_id=job_id, status="started", export_mode=export_mode)


@router.get("/jobs/{job_id}/status", response_model=PipelineStatusResponse)
async def pipeline_status(job_id: str) -> PipelineStatusResponse:
    settings = get_settings()
    pipeline = PipelineProgressTracker(settings).read(job_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    transcription = TranscriptionProgressTracker(settings).read(job_id)
    analysis = AnalysisProgressTracker(settings).read(job_id)

    if pipeline.stage == "transcribing" and transcription is not None:
        if transcription.status == "transcribing" and transcription.progress_percent > 0:
            pipeline = pipeline.model_copy(
                update={
                    "progress_percent": min(
                        25.0 + transcription.progress_percent * 0.35,
                        59.9,
                    ),
                    "message": transcription.message or pipeline.message,
                }
            )
    elif pipeline.stage == "ai_editing" and analysis is not None:
        if analysis.status not in {"queued", "completed", "failed"}:
            pipeline = pipeline.model_copy(
                update={
                    "progress_percent": min(60.0 + analysis.elapsed_sec, 84.9),
                    "message": analysis.message or pipeline.message,
                }
            )

    return PipelineStatusResponse(
        pipeline=pipeline,
        transcription=transcription,
        analysis=analysis,
    )


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
async def job_result(job_id: str) -> JobResultResponse:
    settings = get_settings()
    pipeline = PipelineProgressTracker(settings).read(job_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if pipeline.stage == "failed":
        raise HTTPException(status_code=422, detail=pipeline.error or "Pipeline failed.")
    if pipeline.stage != "completed":
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' is not completed yet.")

    transcript_path = settings.storage_path / job_id / "transcript.json"
    edit_plan_path = settings.storage_path / job_id / "edit_plan.json"
    xml_path = settings.storage_path / job_id / "neurocut_export.xml"
    clips_zip_path = settings.storage_path / job_id / "neurocut_clips.zip"
    clips_dir_path = settings.storage_path / job_id / "clips_export"
    render_path = settings.storage_path / job_id / "neurocut_render.mp4"

    visual_timeline_path = settings.storage_path / job_id / "visual_timeline.json"

    if not transcript_path.is_file() or not edit_plan_path.is_file():
        raise HTTPException(status_code=404, detail=f"Result files missing for job '{job_id}'.")

    export_mode = pipeline.export_mode
    if export_mode == "xml" and not xml_path.is_file():
        raise HTTPException(status_code=404, detail=f"XML export missing for job '{job_id}'.")
    if export_mode == "clips" and not clips_zip_path.is_file():
        raise HTTPException(status_code=404, detail=f"Clips export missing for job '{job_id}'.")
    if export_mode == "render" and not render_path.is_file():
        raise HTTPException(status_code=404, detail=f"Render missing for job '{job_id}'.")

    transcript_payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    plan = EditPlan.model_validate_json(edit_plan_path.read_text(encoding="utf-8"))
    segments = [
        TranscriptSegmentResponse(**segment)
        for segment in transcript_payload.get("segments", [])
    ]

    original_candidates = list((settings.storage_path / job_id).glob("original.*"))
    original_path = pipeline.original_path or (
        str(original_candidates[0]) if original_candidates else ""
    )

    return JobResultResponse(
        job_id=job_id,
        prompt=pipeline.prompt or "",
        export_mode=export_mode,
        analysis_mode=pipeline.analysis_mode,
        original_path=original_path,
        transcript_path=str(transcript_path),
        visual_timeline_path=(
            pipeline.visual_timeline_path
            if pipeline.visual_timeline_path
            else (str(visual_timeline_path) if visual_timeline_path.is_file() else None)
        ),
        edit_plan_path=str(edit_plan_path),
        xml_path=str(xml_path) if xml_path.is_file() else None,
        clips_dir_path=(
            pipeline.clips_dir_path
            if pipeline.clips_dir_path
            else (str(clips_dir_path) if clips_dir_path.is_dir() else None)
        ),
        clips_zip_path=(
            pipeline.clips_zip_path
            if pipeline.clips_zip_path
            else (str(clips_zip_path) if clips_zip_path.is_file() else None)
        ),
        render_path=(
            pipeline.render_path
            if pipeline.render_path
            else (str(render_path) if render_path.is_file() else None)
        ),
        language=transcript_payload.get("language"),
        duration=transcript_payload.get("duration"),
        clip_count=pipeline.clip_count or len(plan.clips),
        marker_count=pipeline.marker_count or len(plan.markers),
        fps=pipeline.fps,
        timebase=pipeline.timebase,
        edit_plan=plan,
        transcript=segments,
    )


@router.post("/jobs/transcribe", response_model=TranscribeJobStartResponse, status_code=202)
async def start_transcribe_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> TranscribeJobStartResponse:
    settings = get_settings()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    job_id = uuid4().hex
    job_dir = settings.ensure_storage() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".mp4"
    upload_path = job_dir / f"original{suffix}"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    upload_path.write_bytes(content)
    save_source_media(
        job_dir,
        original_filename=file.filename,
        stored_filename=upload_path.name,
    )

    TranscriptionProgressTracker(settings).queue(job_id)
    background_tasks.add_task(_run_transcribe_only_job, job_id, upload_path, settings)
    logger.info("[transcribe-only] job=%s queued", job_id)
    return TranscribeJobStartResponse(job_id=job_id, status="started")


@router.post("/media/process", response_model=MediaProcessingResponse)
async def process_media(file: UploadFile = File(...)) -> MediaProcessingResponse:
    settings = get_settings()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    job_id = uuid4().hex
    job_dir = settings.ensure_storage() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix or ".mp4"
    upload_path = job_dir / f"original{suffix}"

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        upload_path.write_bytes(content)
        save_source_media(
            job_dir,
            original_filename=file.filename,
            stored_filename=upload_path.name,
        )

        processor = MediaProcessor(settings)
        media_result = processor.process_video(upload_path, job_id=job_id)
    except MediaProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during media processing: {exc}",
        ) from exc

    logger.info("[media] job=%s prepared audio and proxy", job_id)

    return MediaProcessingResponse(
        job_id=media_result.job_id,
        original_path=str(media_result.original_path),
        audio_path=str(media_result.audio_path) if media_result.audio_path else None,
        proxy_video_path=str(media_result.proxy_video_path),
        has_audio=media_result.has_audio,
        duration_sec=media_result.duration_sec,
    )


@router.post("/jobs/{job_id}/transcribe", response_model=TranscriptionStartResponse, status_code=202)
async def start_transcription(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> TranscriptionStartResponse:
    settings = get_settings()
    audio_path = settings.storage_path / job_id / "audio.wav"
    original_candidates = sorted(
        path
        for path in (settings.storage_path / job_id).glob("original.*")
        if path.is_file()
    )
    if not audio_path.is_file():
        if not original_candidates:
            raise HTTPException(status_code=404, detail=f"Job media not found for '{job_id}'.")
        processor = MediaProcessor(settings)
        has_audio, _ = processor._probe_media(original_candidates[0])
        if has_audio:
            raise HTTPException(status_code=404, detail=f"Audio file not found for job '{job_id}'.")

    tracker = TranscriptionProgressTracker(settings)
    current = tracker.read(job_id)
    if current and current.status in {"queued", "loading_model", "transcribing"}:
        raise HTTPException(
            status_code=409,
            detail=f"Transcription already in progress for job '{job_id}'.",
        )

    tracker.queue(job_id)
    background_tasks.add_task(_run_transcription_job, job_id, settings)
    logger.info("[transcribe] job=%s queued", job_id)
    return TranscriptionStartResponse(job_id=job_id, status="started")


@router.get("/jobs/{job_id}/transcription/status")
async def transcription_status(job_id: str):
    settings = get_settings()
    state = TranscriptionProgressTracker(settings).read(job_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"No transcription progress found for job '{job_id}'.",
        )
    return state


@router.get("/jobs/{job_id}/transcription/result", response_model=TranscriptionResultResponse)
async def transcription_result(job_id: str) -> TranscriptionResultResponse:
    settings = get_settings()
    transcript_path = settings.storage_path / job_id / "transcript.json"
    if not transcript_path.is_file():
        tracker = TranscriptionProgressTracker(settings)
        state = tracker.read(job_id)
        if state and state.status == "failed":
            raise HTTPException(status_code=422, detail=state.error or "Transcription failed.")
        raise HTTPException(
            status_code=404,
            detail=f"Transcript not ready for job '{job_id}'.",
        )

    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = [
        TranscriptSegmentResponse(**segment)
        for segment in payload.get("segments", [])
    ]
    return TranscriptionResultResponse(
        job_id=job_id,
        transcript_path=str(transcript_path),
        language=payload.get("language"),
        duration=payload.get("duration"),
        elapsed_sec=payload.get("elapsed_sec"),
        device=payload.get("device"),
        compute_type=payload.get("compute_type"),
        segment_count=len(segments),
        transcript=segments,
    )


@router.get("/jobs/{job_id}/transcript", response_model=TranscriptResponse)
async def get_job_transcript(job_id: str) -> TranscriptResponse:
    settings = get_settings()
    transcript_path = settings.storage_path / job_id / "transcript.json"
    if not transcript_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Transcript not found for job '{job_id}'.",
        )

    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = [
        TranscriptSegmentResponse(**segment)
        for segment in payload.get("segments", [])
    ]
    return TranscriptResponse(
        job_id=job_id,
        source=payload.get("source", "speech"),
        has_speech=payload.get("has_speech", bool(segments)),
        file_hash=payload.get("file_hash"),
        cached=payload.get("cached", False),
        language=payload.get("language"),
        duration=payload.get("duration"),
        segment_count=len(segments),
        transcript=segments,
    )


@router.post("/transcripts", response_model=TranscriptUploadResponse, status_code=201)
async def upload_transcript(
    file: UploadFile = File(...),
    job_id: str | None = Form(default=None),
    file_hash: str | None = Form(default=None),
) -> TranscriptUploadResponse:
    settings = get_settings()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded transcript is empty.")

    if job_id is not None and not (settings.storage_path / job_id).is_dir():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    service = STTService(settings)
    try:
        transcript = service.parse_transcript_file(file.filename or "transcript", content)
    except STTServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    written = service.store_uploaded_transcript(
        transcript,
        job_id=job_id,
        file_hash=file_hash,
    )
    segments = [
        TranscriptSegmentResponse(start=s.start, end=s.end, text=s.text)
        for s in transcript.segments
    ]
    logger.info(
        "[transcripts] uploaded segments=%d job=%s hash=%s",
        len(segments),
        job_id,
        (file_hash or "")[:12],
    )
    return TranscriptUploadResponse(
        job_id=job_id,
        file_hash=file_hash,
        segment_count=len(segments),
        duration=transcript.duration,
        transcript_path=written.get("transcript_path"),
        cache_path=written.get("cache_path"),
        transcript=segments,
    )


@router.post("/jobs/{job_id}/analyze", response_model=AnalysisStartResponse, status_code=202)
async def start_analysis(
    job_id: str,
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> AnalysisStartResponse:
    settings = get_settings()
    transcript_path = settings.storage_path / job_id / "transcript.json"
    proxy_video_path = settings.storage_path / job_id / "proxy_480p.mp4"
    if not transcript_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Transcript not found for job '{job_id}'. Run transcription first.",
        )
    if not proxy_video_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Proxy video not found for job '{job_id}'.",
        )

    tracker = AnalysisProgressTracker(settings)
    current = tracker.read(job_id)
    if current and current.status in {
        "queued",
        "uploading_video",
        "waiting_video",
        "analyzing",
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Analysis already in progress for job '{job_id}'.",
        )

    tracker.queue(
        job_id,
        max_attempts=settings.gemini_max_retries,
        model=settings.resolved_analysis_model_label,
    )
    background_tasks.add_task(_run_analysis_job, job_id, request.prompt, settings)
    logger.info("[analyze] job=%s queued", job_id)
    return AnalysisStartResponse(job_id=job_id, status="started")


@router.get("/jobs/{job_id}/analysis/status")
async def analysis_status(job_id: str):
    settings = get_settings()
    state = AnalysisProgressTracker(settings).read(job_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis progress found for job '{job_id}'.",
        )
    return state


@router.get("/jobs/{job_id}/analysis/result", response_model=AnalysisResultResponse)
async def analysis_result(job_id: str) -> AnalysisResultResponse:
    settings = get_settings()
    edit_plan_path = settings.storage_path / job_id / "edit_plan.json"
    if not edit_plan_path.is_file():
        tracker = AnalysisProgressTracker(settings)
        state = tracker.read(job_id)
        if state and state.status == "failed":
            raise HTTPException(status_code=422, detail=state.error or "Analysis failed.")
        raise HTTPException(
            status_code=404,
            detail=f"Edit plan not ready for job '{job_id}'.",
        )

    payload = json.loads(edit_plan_path.read_text(encoding="utf-8"))
    plan = EditPlan.model_validate(payload)
    tracker = AnalysisProgressTracker(settings)
    state = tracker.read(job_id)

    return AnalysisResultResponse(
        job_id=job_id,
        edit_plan_path=str(edit_plan_path),
        clips_count=len(plan.clips),
        markers_count=len(plan.markers),
        elapsed_sec=state.elapsed_sec if state else None,
        model=state.model if state else settings.resolved_analysis_model_label,
        edit_plan=plan,
    )


@router.post("/jobs/{job_id}/export/xml", response_model=XMLExportResponse)
async def export_xml(job_id: str) -> XMLExportResponse:
    settings = get_settings()
    try:
        result = XMLGenerator(settings).generate(job_id, save=True)
    except XMLGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during XML export: {exc}",
        ) from exc

    return XMLExportResponse(
        job_id=result.job_id,
        xml_path=str(result.xml_path),
        clip_count=result.clip_count,
        marker_count=result.marker_count,
        sequence_duration_frames=result.sequence_duration_frames,
        fps=result.fps,
        timebase=result.timebase,
    )


@router.get("/jobs/{job_id}/export/xml/download")
async def download_xml(job_id: str) -> FileResponse:
    settings = get_settings()
    try:
        package = XMLGenerator(settings).create_download_package(job_id)
    except XMLGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during XML package export: {exc}",
        ) from exc

    return FileResponse(
        path=package.zip_path,
        media_type="application/zip",
        filename=f"neurocut_{job_id[:8]}_nle.zip",
    )


@router.post("/jobs/{job_id}/export/clips", response_model=ClipExportResponse)
async def export_clips(job_id: str) -> ClipExportResponse:
    settings = get_settings()
    try:
        result = ClipExporter(settings).generate(job_id, save=True)
    except ClipExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during clip export: {exc}",
        ) from exc

    return ClipExportResponse(
        job_id=result.job_id,
        clips_dir=str(result.clips_dir),
        zip_path=str(result.zip_path),
        manifest_path=str(result.manifest_path),
        clip_count=result.clip_count,
        marker_count=result.marker_count,
    )


@router.get("/jobs/{job_id}/export/clips/download")
async def download_clips(job_id: str) -> FileResponse:
    settings = get_settings()
    zip_path = settings.storage_path / job_id / "neurocut_clips.zip"
    if not zip_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Clips export not found for job '{job_id}'. Generate export first.",
        )
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"neurocut_{job_id[:8]}_clips.zip",
    )


@router.post("/jobs/{job_id}/export/render", response_model=RenderExportResponse)
async def export_render(job_id: str) -> RenderExportResponse:
    settings = get_settings()
    try:
        result = VideoRenderer(settings).render(job_id, save=True)
    except VideoRenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during render: {exc}",
        ) from exc

    return RenderExportResponse(
        job_id=result.job_id,
        render_path=str(result.render_path),
        clip_count=result.clip_count,
        duration_sec=result.duration_sec,
    )


@router.get("/jobs/{job_id}/export/render/download")
async def download_render(job_id: str) -> FileResponse:
    settings = get_settings()
    render_path = settings.storage_path / job_id / "neurocut_render.mp4"
    if not render_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Render not found for job '{job_id}'. Generate render first.",
        )
    return FileResponse(
        path=render_path,
        media_type="video/mp4",
        filename=f"neurocut_{job_id[:8]}_render.mp4",
    )


@router.post(
    "/jobs/{job_id}/subtitles/chunk",
    response_model=SubtitleChunkResponse,
)
async def preview_subtitle_chunks(
    job_id: str,
    request: SubtitleChunkRequest,
) -> SubtitleChunkResponse:
    """Preview karaoke-style word chunking without burning.

    Uses the real frame width so the editor shows exactly what will be
    rendered (1..max_words words per line, timed to speech).
    """
    settings = get_settings()
    job_dir = settings.storage_path / job_id
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    original_candidates = sorted(job_dir.glob("original.*"))
    if not original_candidates:
        raise HTTPException(
            status_code=404,
            detail=f"Original video not found for job '{job_id}'.",
        )

    from app.utils.subtitle_chunker import char_budget, chunk_subtitle_segments

    burner = SubtitleBurner(settings)
    frame_width = burner._probe_frame_width(original_candidates[0])
    style = burner.default_style()
    segments = [
        SubtitleSegment(start=s.start, end=s.end, text=s.text)
        for s in request.segments
        if s.text.strip()
    ]
    chunked = chunk_subtitle_segments(
        segments,
        frame_width=frame_width,
        font_size=style.font_size,
        char_ratio=settings.subtitle_char_ratio,
        side_margin=settings.subtitle_side_margin,
        max_words=request.max_words or settings.subtitle_max_words,
    )
    budget = char_budget(
        frame_width,
        style.font_size,
        char_ratio=settings.subtitle_char_ratio,
        side_margin=settings.subtitle_side_margin,
    )
    out_segments = [
        SubtitleChunkSegment(
            start=round(s.start, 3),
            end=round(s.end, 3),
            text=s.text,
            overflow=len(s.text) > budget,
        )
        for s in chunked
    ]
    return SubtitleChunkResponse(
        job_id=job_id,
        frame_width=frame_width,
        font_size=style.font_size,
        char_budget=budget,
        segment_count=len(out_segments),
        overflow_count=sum(1 for s in out_segments if s.overflow),
        segments=out_segments,
    )


@router.get("/subtitles/fonts", response_model=SubtitleFontsResponse)
async def list_subtitle_fonts() -> SubtitleFontsResponse:
    return SubtitleFontsResponse(
        fonts=[SubtitleFont(**font) for font in available_fonts()]
    )


@router.get("/subtitles/fonts/{name}/file")
async def get_subtitle_font_file(name: str) -> FileResponse:
    """Serve the exact TTF used for burn-in so the UI preview matches 1:1."""
    import shutil
    import subprocess

    allowed = {font["name"] for font in available_fonts()}
    if name not in allowed:
        raise HTTPException(status_code=404, detail=f"Unknown font '{name}'.")

    fc_match = shutil.which("fc-match")
    if fc_match is None:
        raise HTTPException(status_code=500, detail="fontconfig is not available.")

    try:
        result = subprocess.run(
            [fc_match, "-f", "%{file}", name],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:  # noqa: PERF203
        raise HTTPException(
            status_code=404, detail=f"Font '{name}' not resolved."
        ) from exc

    font_path = Path(result.stdout.strip())
    if not font_path.is_file():
        raise HTTPException(status_code=404, detail=f"Font file for '{name}' missing.")

    media_type = "font/ttf" if font_path.suffix.lower() == ".ttf" else "font/otf"
    return FileResponse(
        path=font_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/subtitles/proofread", response_model=SubtitleProofreadResponse)
async def proofread_subtitles(
    request: SubtitleProofreadRequest,
) -> SubtitleProofreadResponse:
    """Fix spelling and punctuation of subtitle lines via Gemini.

    Segment count and timings are preserved; only the text is corrected.
    """
    settings = get_settings()
    originals = [s.text for s in request.segments]
    try:
        corrected = TextProofreader(settings).proofread(
            originals, language=request.language
        )
    except ProofreadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    from app.utils.subtitle_chunker import split_segments_into_sentences

    corrected_segments = [
        SubtitleSegment(start=src.start, end=src.end, text=text or src.text)
        for src, text in zip(request.segments, corrected)
    ]
    # Rule: a full stop starts a new line; never mix two sentences on one line.
    split = split_segments_into_sentences(corrected_segments)
    if not split:
        split = corrected_segments

    text_changed = any(a.strip() != b.strip() for a, b in zip(originals, corrected))
    changed = text_changed or len(split) != len(request.segments)
    segments = [
        TranscriptSegmentResponse(
            start=round(s.start, 3),
            end=round(s.end, 3),
            text=s.text,
        )
        for s in split
    ]
    return SubtitleProofreadResponse(segments=segments, changed=changed)


@router.post(
    "/jobs/{job_id}/subtitles/render",
    response_model=SubtitleRenderStartResponse,
    status_code=202,
)
async def start_subtitle_render(
    job_id: str,
    request: SubtitleRenderRequest,
    background_tasks: BackgroundTasks,
) -> SubtitleRenderStartResponse:
    settings = get_settings()
    job_dir = settings.storage_path / job_id
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    original_candidates = sorted(job_dir.glob("original.*"))
    if not original_candidates:
        raise HTTPException(
            status_code=404,
            detail=f"Original video not found for job '{job_id}'.",
        )

    tracker = SubtitleProgressTracker(settings)
    current = tracker.read(job_id)
    if current and current.status in {"queued", "burning"}:
        raise HTTPException(
            status_code=409,
            detail=f"Subtitle render already in progress for job '{job_id}'.",
        )

    segments = [
        SubtitleSegment(start=s.start, end=s.end, text=s.text)
        for s in request.segments
    ]

    style: SubtitleStyle | None = None
    if request.style is not None:
        base = SubtitleBurner(settings).default_style()
        style = SubtitleStyle(
            font_size=request.style.font_size or base.font_size,
            primary_color=request.style.primary_color or base.primary_color,
            outline_color=request.style.outline_color or base.outline_color,
            outline=request.style.outline if request.style.outline is not None else base.outline,
            margin_v=request.style.margin_v if request.style.margin_v is not None else base.margin_v,
            font_name=request.style.font_name or base.font_name,
            border_style=(
                request.style.border_style
                if request.style.border_style in (1, 3)
                else base.border_style
            ),
        )

    tracker.queue(job_id, segment_count=len(segments))
    background_tasks.add_task(
        _run_subtitle_job,
        job_id,
        segments,
        style,
        settings,
        auto_chunk=request.auto_chunk,
        max_words=request.max_words,
    )
    logger.info("[subtitles] job=%s queued segments=%d", job_id, len(segments))
    return SubtitleRenderStartResponse(
        job_id=job_id,
        status="started",
        segment_count=len(segments),
    )


@router.get("/jobs/{job_id}/subtitles/status")
async def subtitle_status(job_id: str):
    settings = get_settings()
    state = SubtitleProgressTracker(settings).read(job_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"No subtitle progress found for job '{job_id}'.",
        )
    return state


@router.get("/jobs/{job_id}/subtitles/download")
async def download_subtitled(job_id: str) -> FileResponse:
    settings = get_settings()
    output_path = settings.storage_path / job_id / "neurocut_subtitled.mp4"
    if not output_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Subtitled video not found for job '{job_id}'.",
        )
    return FileResponse(
        path=output_path,
        media_type="video/mp4",
        filename=f"neurocut_{job_id[:8]}_subtitled.mp4",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@router.post("/jobs/{job_id}/analyze/scenes", response_model=SceneDetectionResponse)
async def analyze_scenes(job_id: str) -> SceneDetectionResponse:
    settings = get_settings()
    job_dir = settings.storage_path / job_id
    proxy_video_path = job_dir / "proxy_480p.mp4"
    if not proxy_video_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Proxy video not found for job '{job_id}'. Run media processing first.",
        )

    scene_proxy_path = job_dir / settings.scene_proxy_filename
    detection_video = (
        scene_proxy_path if scene_proxy_path.is_file() else proxy_video_path
    )

    try:
        result = SceneDetector(settings).detect(
            detection_video,
            job_id=job_id,
            save=True,
        )
    except SceneDetectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error during scene detection: {exc}",
        ) from exc

    timeline = json.loads(result.timeline_path.read_text(encoding="utf-8"))
    return SceneDetectionResponse(
        job_id=result.job_id,
        timeline_path=str(result.timeline_path),
        shot_count=result.shot_count,
        duration=result.duration,
        scene_threshold=float(timeline.get("scene_threshold", settings.scene_threshold)),
    )
