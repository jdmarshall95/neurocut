from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.metrics import observe_stage, record_job
from app.models.visual_timeline import TimelineSource
from app.utils.edit_plan_normalize import is_sparse_speech
from app.services.ai_analyzer import AIAnalysisError, AIAnalyzer
from app.services.analysis_progress import AnalysisProgressTracker
from app.services.clip_exporter import ClipExportError, ClipExporter
from app.services.media_processor import MediaProcessingError, MediaProcessor
from app.services.pipeline_progress import ExportMode, PipelineProgressTracker
from app.services.scene_detector import SceneDetectionError, SceneDetector
from app.services.stt_service import STTOptions, STTService, STTServiceError
from app.services.transcriber import TranscriptionError, Transcriber
from app.services.transcription_progress import TranscriptionProgressTracker
from app.services.video_renderer import VideoRenderError, VideoRenderer
from app.services.xml_generator import XMLGenerationError

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when the end-to-end pipeline fails."""


class PipelineRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.progress = PipelineProgressTracker(self.settings)

    @staticmethod
    def _transcript_is_uploaded(transcript_path: Path) -> bool:
        import json

        try:
            payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return payload.get("source") == "uploaded"

    def _resolve_analysis_mode(
        self,
        transcription_result,
    ) -> TimelineSource:
        if is_sparse_speech(
            transcription_result.segments,
            transcription_result.duration,
        ):
            return "visual"
        return "speech"

    def run(
        self,
        job_id: str,
        prompt: str,
        upload_path: Path | list[Path],
        *,
        export_mode: ExportMode = "xml",
        reference_source: bool = False,
    ) -> None:
        started = time.perf_counter()
        stt_engine = "whisper"
        outcome = "failed"
        try:
            self.progress.set_stage(job_id, "extracting_audio", export_mode=export_mode)
            processor = MediaProcessor(self.settings)
            paths = upload_path if isinstance(upload_path, list) else [upload_path]
            if len(paths) > 1:
                media_result = processor.process_multiple_videos(paths, job_id=job_id)
            else:
                media_result = processor.process_video(
                    paths[0],
                    job_id=job_id,
                    reference_source=reference_source,
                )
            self.progress.set_stage(
                job_id,
                "extracting_audio",
                original_path=str(media_result.original_path),
            )

            transcript_path = self.settings.storage_path / job_id / "transcript.json"
            transcriber = Transcriber(self.settings)
            stt_service = STTService(self.settings)
            stt_engine = stt_service._resolve_engine(None)

            if (
                self.settings.skip_stt_if_transcript_provided
                and transcript_path.is_file()
                and self._transcript_is_uploaded(transcript_path)
            ):
                self.progress.set_stage(
                    job_id,
                    "transcribing",
                    message="Using uploaded transcript, skipping STT...",
                )
                transcription_result = transcriber.load_transcript(job_id)
                analysis_mode = self._resolve_analysis_mode(transcription_result)
            elif media_result.has_audio and media_result.audio_path is not None:
                self.progress.set_stage(job_id, "transcribing")
                stt_transcript = stt_service.transcribe(
                    media_result.audio_path,
                    STTOptions(),
                    job_id=job_id,
                )
                stt_engine = stt_transcript.engine or stt_engine
                transcription_result = transcriber.load_transcript(job_id)
                if stt_transcript.cached:
                    self.progress.set_stage(
                        job_id,
                        "transcribing",
                        message="Transcript loaded from cache",
                    )
                analysis_mode = self._resolve_analysis_mode(transcription_result)
            else:
                self.progress.set_stage(
                    job_id,
                    "transcribing",
                    message="No audio track, skipping transcription...",
                )
                transcription_result = transcriber.record_no_audio(
                    job_id=job_id,
                    duration=media_result.duration_sec,
                    save=True,
                )
                analysis_mode = "visual"

            visual_timeline_path: Path | None = None

            self.progress.set_stage(
                job_id,
                "transcribing",
                transcript_path=str(transcript_path),
                analysis_mode=analysis_mode,
                progress_percent=55.0 if analysis_mode == "speech" else 40.0,
            )

            sparse_speech = bool(
                media_result.has_audio and transcription_result.segments
            )
            scene_message = (
                "Scene detection (lightweight proxy, low FPS)..."
                if analysis_mode == "speech"
                else (
                    "Little or no speech. Analyzing visuals and detecting scenes..."
                    if sparse_speech
                    else "No speech detected. Analyzing visuals and detecting scenes..."
                )
            )
            self.progress.set_stage(
                job_id,
                "analyzing_scenes",
                analysis_mode=analysis_mode,
                message=scene_message,
            )
            scene_video = (
                media_result.scene_proxy_video_path
                if media_result.scene_proxy_video_path is not None
                else media_result.proxy_video_path
            )
            scene_result = SceneDetector(self.settings).detect(
                scene_video,
                job_id=job_id,
                save=True,
            )
            visual_timeline_path = scene_result.timeline_path
            self.progress.set_stage(
                job_id,
                "analyzing_scenes",
                visual_timeline_path=str(visual_timeline_path),
                progress_percent=58.0,
            )

            self.progress.set_stage(job_id, "ai_editing", analysis_mode=analysis_mode)
            analyzer = AIAnalyzer(self.settings)
            plan = analyzer.analyze(
                job_id,
                prompt,
                analysis_mode=analysis_mode,
                save=True,
            )
            edit_plan_path = self.settings.storage_path / job_id / "edit_plan.json"
            self.progress.set_stage(
                job_id,
                "ai_editing",
                edit_plan_path=str(edit_plan_path),
                progress_percent=85.0,
            )

            completion_fields: dict[str, object] = {
                "original_path": str(media_result.original_path),
                "transcript_path": str(transcript_path),
                "edit_plan_path": str(edit_plan_path),
                "analysis_mode": analysis_mode,
                "clip_count": len(plan.clips),
                "marker_count": len(plan.markers),
            }
            if visual_timeline_path is not None:
                completion_fields["visual_timeline_path"] = str(visual_timeline_path)

            if export_mode == "clips":
                self.progress.set_stage(job_id, "generating_clips")
                clip_export = ClipExporter(self.settings).generate(job_id, save=True)
                self.progress.complete(
                    job_id,
                    clips_dir_path=str(clip_export.clips_dir),
                    clips_zip_path=str(clip_export.zip_path),
                    **completion_fields,
                )
                logger.info(
                    "[pipeline] job=%s completed mode=clips analysis=%s clips=%d zip=%s",
                    job_id,
                    analysis_mode,
                    len(plan.clips),
                    clip_export.zip_path,
                )
                outcome = "success"
                return

            if export_mode == "render":
                self.progress.set_stage(job_id, "rendering_clip")
                render = VideoRenderer(self.settings).render(job_id, save=True)
                self.progress.complete(
                    job_id,
                    render_path=str(render.render_path),
                    **completion_fields,
                )
                logger.info(
                    "[pipeline] job=%s completed mode=render analysis=%s clips=%d out=%s",
                    job_id,
                    analysis_mode,
                    len(plan.clips),
                    render.render_path,
                )
                outcome = "success"
                return

            if export_mode == "plugin":
                from app.services.xml_generator import XMLGenerator

                metadata = XMLGenerator(self.settings)._probe_video(
                    media_result.original_path
                )
                fps = metadata.fps or self.settings.default_fps
                self.progress.set_stage(
                    job_id,
                    "applying_timeline",
                    message="Edit plan ready. Apply in Premiere.",
                    progress_percent=95.0,
                )
                self.progress.complete(
                    job_id,
                    fps=fps,
                    **completion_fields,
                )
                logger.info(
                    "[pipeline] job=%s completed mode=plugin analysis=%s clips=%d markers=%d",
                    job_id,
                    analysis_mode,
                    len(plan.clips),
                    len(plan.markers),
                )
                outcome = "success"
                return

            self.progress.set_stage(job_id, "generating_xml")
            export = XMLGenerator(self.settings).generate(job_id, save=True)
            self.progress.complete(
                job_id,
                xml_path=str(export.xml_path),
                fps=export.fps,
                timebase=export.timebase,
                **completion_fields,
            )
            logger.info(
                "[pipeline] job=%s completed mode=xml analysis=%s clips=%d markers=%d xml=%s",
                job_id,
                analysis_mode,
                len(plan.clips),
                len(plan.markers),
                export.xml_path,
            )
            outcome = "success"
        except (
            MediaProcessingError,
            TranscriptionError,
            STTServiceError,
            SceneDetectionError,
            AIAnalysisError,
            XMLGenerationError,
            ClipExportError,
            VideoRenderError,
        ) as exc:
            logger.exception("[pipeline] job=%s failed: %s", job_id, exc)
            self.progress.fail(job_id, str(exc))
            self._fail_subtasks(job_id, str(exc))
        except Exception as exc:
            logger.exception("[pipeline] job=%s unexpected error", job_id)
            message = f"Unexpected pipeline error: {exc}"
            self.progress.fail(job_id, message)
            self._fail_subtasks(job_id, message)
        finally:
            elapsed = time.perf_counter() - started
            observe_stage("pipeline", elapsed)
            record_job(status=outcome, engine=stt_engine)
            logger.info(
                "[pipeline] job=%s finished status=%s engine=%s elapsed=%.2fs",
                job_id,
                outcome,
                stt_engine,
                elapsed,
            )

    def _fail_subtasks(self, job_id: str, error: str) -> None:
        transcription = TranscriptionProgressTracker(self.settings).read(job_id)
        if transcription and transcription.status not in {"completed", "failed"}:
            TranscriptionProgressTracker(self.settings).fail(job_id, error)

        analysis = AnalysisProgressTracker(self.settings).read(job_id)
        if analysis and analysis.status not in {"completed", "failed"}:
            AnalysisProgressTracker(self.settings).fail(job_id, error)


def run_pipeline_job(
    job_id: str,
    prompt: str,
    upload_path: Path | list[Path],
    settings: Settings | None = None,
    *,
    export_mode: ExportMode = "xml",
    reference_source: bool = False,
) -> None:
    PipelineRunner(settings).run(
        job_id,
        prompt,
        upload_path,
        export_mode=export_mode,
        reference_source=reference_source,
    )
