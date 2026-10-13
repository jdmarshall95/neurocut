from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import Settings, get_settings
from app.core.deepseek_client import DeepSeekClientError, chat_completion_json
from app.core.llm import GeminiClientError, create_gemini_client
from app.models.edit_plan import EditPlan
from app.models.visual_timeline import TimelineSource, VisualShot, VisualTimeline
from app.services.analysis_progress import AnalysisProgressTracker
from app.services.transcriber import TranscriptSegment
from app.utils.edit_plan_normalize import is_sparse_speech, normalize_edit_plan_timestamps

logger = logging.getLogger(__name__)

TIMESTAMP_RULES = """
CRITICAL timestamp format for start_sec, end_sec, and time_sec:
- Unit: absolute SECONDS from the start of the video (not milliseconds, not percent, not frames).
- Precision: exactly ONE decimal place — whole seconds plus tenths.
- Valid examples: 0.0, 1.0, 2.5, 10.0, 12.3, 21.4
- INVALID examples: 0.01 (that is NOT "1 second"), 0.12 (that is NOT "12 seconds"), 1250, 0.5%
- Mapping rule: second 1 -> 1.0, second 2 -> 2.0, second 12.5 -> 12.5
- For a 30.0s video, timestamps must stay within 0.0 .. 30.0
- Each clip should usually be at least 0.5s long unless the brief asks for very fast cuts.
"""

SYSTEM_INSTRUCTION_SPEECH = f"""You are NeuroCut, an expert AI video editing assistant.
Your task is to analyze the user's editing brief, transcript with timestamps,
and detected shot boundaries from scene detection.
You do NOT see the actual video — only text metadata. Never claim visual quality you cannot verify
(blur, sharpness, camera shake). Use shot boundaries as natural cut points.
Return a rough-cut edit plan as strict JSON with selected clips and editorial markers.
Use only timestamps that fit the provided transcript/video duration.
Prefer coherent story flow and remove filler when the brief asks for a tight cut.
{TIMESTAMP_RULES}"""

SYSTEM_INSTRUCTION_VISUAL = f"""You are NeuroCut, an expert AI visual video editing assistant.
The source video has little or no speech. Analyze the proxy video, shot boundaries, and the user's brief.
Build a rough-cut edit plan using visual storytelling: action, composition, scene changes, pacing.
Prefer clip boundaries that align with provided shot boundaries when possible.
Use only timestamps that fit the provided shot timeline/video duration.
Return strict JSON with selected clips and editorial markers.
{TIMESTAMP_RULES}"""


def _edit_plan_schema_hint() -> str:
    return (
        "Return ONLY valid JSON matching this schema (no markdown):\n"
        f"{json.dumps(EditPlan.model_json_schema(), ensure_ascii=False)}"
    )


class AIAnalysisError(Exception):
    """Raised when Gemini analysis fails."""


def _client_error_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    return None


def _is_rate_limit_error(exc: Exception) -> bool:
    return isinstance(exc, genai_errors.ClientError) and _client_error_code(exc) == 429


def _is_model_unavailable_error(exc: Exception) -> bool:
    if _is_transient_error(exc) and not _is_zero_quota_error(exc):
        return False
    if isinstance(exc, genai_errors.ClientError):
        if _client_error_code(exc) in {403, 404}:
            return True
        if _client_error_code(exc) == 429 and _is_zero_quota_error(exc):
            return True
    message = str(exc).lower()
    markers = (
        "limit: 0",
        "not found",
        "is not supported",
        "unsupported model",
        "model not available",
        "no longer available",
        "permission denied",
    )
    return any(marker in message for marker in markers)


def _transient_wait_sec(settings: Settings, attempt: int) -> float:
    base = settings.gemini_rate_limit_wait_sec
    multiplier = settings.gemini_transient_backoff_multiplier
    return min(base * (multiplier ** max(attempt - 1, 0)), base * 4)


def _is_zero_quota_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "limit: 0" in message or "quota exceeded" in message and "free_tier" in message


def _format_gemini_error(exc: Exception, model: str) -> str:
    if _is_rate_limit_error(exc):
        if _is_zero_quota_error(exc):
            return (
                f"Model `{model}` has no free-tier quota available (limit 0). "
                "Will try the next model in the priority list."
            )
        return (
            f"Gemini API rate limit exceeded for model `{model}` (429). "
            "Will try the next model in the priority list."
        )
    return str(exc)


def _should_switch_model(exc: Exception) -> bool:
    if _is_model_unavailable_error(exc):
        return True
    if isinstance(exc, genai_errors.ClientError) and _client_error_code(exc) in {400, 500, 502, 504}:
        message = str(exc).lower()
        return "model" in message
    return False


def _model_supports_video(model: str) -> bool:
    """Montage uses text-out Gemini models — transcript + shot timeline only."""
    return False


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ClientError):
        return _client_error_code(exc) in {429, 503}
    return False


def _is_video_input_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = (
        "video",
        "mime",
        "not support",
        "unsupported",
        "invalid argument",
        "file data",
        "cannot use",
    )
    return any(marker in message for marker in markers)


class AIAnalyzer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.progress = AnalysisProgressTracker(self.settings)

    def _load_transcript_segments(self, job_id: str) -> tuple[list[TranscriptSegment], float | None, bool]:
        transcript_path = self.settings.storage_path / job_id / "transcript.json"
        if not transcript_path.is_file():
            raise AIAnalysisError(
                f"Transcript not found for job '{job_id}'. Run transcription first."
            )

        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        segments = [
            TranscriptSegment.model_validate(segment)
            for segment in payload.get("segments", [])
        ]
        has_speech = payload.get("has_speech", bool(segments))
        duration = payload.get("duration")
        return segments, duration, has_speech

    def _load_visual_timeline(self, job_id: str) -> tuple[list[VisualShot], float | None]:
        timeline_path = self.settings.storage_path / job_id / "visual_timeline.json"
        if not timeline_path.is_file():
            raise AIAnalysisError(
                f"Visual timeline not found for job '{job_id}'. Run scene detection first."
            )

        timeline = VisualTimeline.model_validate_json(timeline_path.read_text(encoding="utf-8"))
        return timeline.shots, timeline.duration

    def _try_load_visual_timeline(
        self,
        job_id: str,
    ) -> tuple[list[VisualShot], float | None] | None:
        timeline_path = self.settings.storage_path / job_id / "visual_timeline.json"
        if not timeline_path.is_file():
            return None
        try:
            timeline = VisualTimeline.model_validate_json(
                timeline_path.read_text(encoding="utf-8")
            )
        except Exception:
            logger.warning(
                "[analyze] job=%s invalid visual_timeline.json, ignoring",
                job_id,
                exc_info=True,
            )
            return None
        return timeline.shots, timeline.duration

    def _format_transcript(self, segments: list[TranscriptSegment]) -> str:
        return "\n".join(
            f"[{segment.start:.1f} -> {segment.end:.1f}] {segment.text}"
            for segment in segments
        )

    def _format_visual_shots(self, shots: list[VisualShot]) -> str:
        return "\n".join(
            f"[{shot.start:.1f} -> {shot.end:.1f}] {shot.label}"
            for shot in shots
        )

    def _timestamp_format_hint(self, duration: float | None) -> str:
        duration_line = f"{duration:.1f}" if duration is not None else "unknown"
        return (
            "Timestamp format (mandatory):\n"
            "- seconds with one decimal place, e.g. 1.0, 5.5, 12.3\n"
            f"- valid range: 0.0 .. {duration_line}\n"
            "- 1 second = 1.0 (NOT 0.01); 12 seconds = 12.0 (NOT 0.12)\n"
        )

    def _build_user_prompt(
        self,
        *,
        task_prompt: str,
        analysis_mode: TimelineSource,
        segments: list[TranscriptSegment] | None = None,
        shots: list[VisualShot] | None = None,
        duration: float | None,
        sources_info: str | None = None,
    ) -> str:
        duration_line = f"{duration:.1f}" if duration is not None else "unknown"
        timestamp_hint = self._timestamp_format_hint(duration)
        sources_block = f"{sources_info}\n\n" if sources_info else ""
        if analysis_mode == "visual":
            return (
                f"{sources_block}"
                "Editing brief:\n"
                f"{task_prompt.strip()}\n\n"
                f"Video duration (seconds): {duration_line}\n"
                "Speech: not detected or negligible.\n\n"
                "Detected shot boundaries (visual timeline):\n"
                f"{self._format_visual_shots(shots or [])}\n\n"
                f"{timestamp_hint}\n"
                "Use shot boundaries as natural cut points when selecting clips.\n"
                "Return ONLY JSON that matches the required schema."
            )

        shots_block = ""
        if shots:
            shots_block = (
                "Detected shot boundaries (scene detection on low-fps proxy):\n"
                f"{self._format_visual_shots(shots)}\n\n"
                "Align clip in/out points with shot boundaries when possible. "
                "Do not invent visual quality judgments — you only have transcript + shot times.\n\n"
            )

        return (
            f"{sources_block}"
            "Editing brief:\n"
            f"{task_prompt.strip()}\n\n"
            f"Video duration (seconds): {duration_line}\n\n"
            f"{shots_block}"
            "Transcript with timestamps:\n"
            f"{self._format_transcript(segments or [])}\n\n"
            f"{timestamp_hint}\n"
            "Return ONLY JSON that matches the required schema."
        )

    def _build_correction_prompt(self, error: str, previous_response: str) -> str:
        return (
            "Your previous response was invalid or did not match the required JSON schema.\n"
            f"Validation error:\n{error}\n\n"
            "Previous response:\n"
            f"{previous_response}\n\n"
            "Fix the JSON. Timestamps must be absolute seconds with ONE decimal place "
            "(1.0 = 1 second, 12.5 = 12.5 seconds; never 0.01 for 1 second).\n"
            "Return ONLY corrected JSON matching the schema. No markdown, no commentary."
        )

    def _extract_json_text(self, raw_text: str) -> str:
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()

    def _parse_edit_plan(self, response: types.GenerateContentResponse) -> EditPlan:
        if response.parsed is not None:
            if isinstance(response.parsed, EditPlan):
                return response.parsed
            return EditPlan.model_validate(response.parsed)

        raw_text = (response.text or "").strip()
        if not raw_text:
            raise AIAnalysisError("Gemini returned an empty response.")

        return EditPlan.model_validate_json(self._extract_json_text(raw_text))

    def _finalize_edit_plan(self, plan: EditPlan, duration: float | None) -> EditPlan:
        return normalize_edit_plan_timestamps(plan, duration)

    def _resolve_analysis_mode(
        self,
        segments: list[TranscriptSegment],
        duration: float | None,
        has_speech: bool,
        requested_mode: TimelineSource | None,
    ) -> TimelineSource:
        if requested_mode is not None:
            return requested_mode
        if not has_speech or not segments:
            return "visual"
        if is_sparse_speech(segments, duration):
            return "visual"
        return "speech"

    def _wait_for_video_file(
        self,
        client,
        uploaded_file: types.File,
        *,
        job_id: str,
        started_at: float,
    ) -> types.File:
        deadline = time.monotonic() + self.settings.gemini_video_wait_timeout_sec
        while time.monotonic() < deadline:
            current = client.files.get(name=uploaded_file.name)
            state = current.state
            if state == types.FileState.ACTIVE:
                self.progress.update(
                    job_id,
                    status="analyzing",
                    message="Video processed by Gemini, starting analysis...",
                    elapsed_sec=time.monotonic() - started_at,
                )
                return current
            if state == types.FileState.FAILED:
                raise AIAnalysisError(
                    f"Gemini video processing failed: {current.error or 'unknown error'}"
                )

            self.progress.update(
                job_id,
                status="waiting_video",
                message="Waiting for Gemini to process the video...",
                elapsed_sec=time.monotonic() - started_at,
            )
            time.sleep(self.settings.gemini_video_poll_interval_sec)

        raise AIAnalysisError("Timed out waiting for Gemini to process the proxy video.")

    def _upload_proxy_video(
        self,
        client,
        proxy_video_path: Path,
        *,
        job_id: str,
        started_at: float,
    ) -> types.File:
        self.progress.update(
            job_id,
            status="uploading_video",
            message="Uploading proxy video to Gemini...",
            elapsed_sec=time.monotonic() - started_at,
        )
        logger.info("[analyze] job=%s uploading proxy video %s", job_id, proxy_video_path)

        uploaded = client.files.upload(
            file=str(proxy_video_path),
            config=types.UploadFileConfig(
                display_name=f"neurocut-{job_id}",
                mime_type="video/mp4",
            ),
        )
        return self._wait_for_video_file(
            client,
            uploaded,
            job_id=job_id,
            started_at=started_at,
        )

    def _generate_edit_plan(
        self,
        client,
        *,
        video_file: types.File | None,
        prompt_text: str,
        analysis_mode: TimelineSource,
        model: str,
        attempt: int,
        job_id: str,
        started_at: float,
    ) -> tuple[EditPlan, str]:
        mode_label = "video" if video_file is not None else "text"
        self.progress.update(
            job_id,
            status="analyzing",
            attempt=attempt,
            model=model,
            message=f"AI analyzing {mode_label} ({model}, attempt {attempt})...",
            elapsed_sec=time.monotonic() - started_at,
        )
        logger.info(
            "[analyze] job=%s model=%s generate_content attempt=%d mode=%s video=%s",
            job_id,
            model,
            attempt,
            analysis_mode,
            video_file is not None,
        )

        system_instruction = (
            SYSTEM_INSTRUCTION_VISUAL
            if analysis_mode == "visual"
            else SYSTEM_INSTRUCTION_SPEECH
        )

        contents: list[object] = []
        if video_file is not None:
            contents.append(
                types.Part.from_uri(
                    file_uri=video_file.uri,
                    mime_type=video_file.mime_type or "video/mp4",
                )
            )
        contents.append(prompt_text)

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=EditPlan,
                temperature=self.settings.gemini_temperature,
            ),
        )

        raw_text = (response.text or "").strip()
        plan = self._parse_edit_plan(response)
        return plan, raw_text

    def _save_edit_plan(self, job_id: str, plan: EditPlan) -> Path:
        output_path = self.settings.storage_path / job_id / "edit_plan.json"
        output_path.write_text(
            plan.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return output_path

    def analyze(
        self,
        job_id: str,
        task_prompt: str,
        *,
        analysis_mode: TimelineSource | None = None,
        segments_override: list[TranscriptSegment] | None = None,
        duration_override: float | None = None,
        save: bool = True,
    ) -> EditPlan:
        if not task_prompt.strip():
            raise AIAnalysisError("Task brief must not be empty.")

        started_at = time.monotonic()
        job_dir = self.settings.storage_path / job_id
        proxy_video_path = job_dir / "proxy_480p.mp4"

        if segments_override is not None:
            segments = segments_override
            duration = duration_override
            has_speech = bool(segments_override)
        else:
            segments, duration, has_speech = self._load_transcript_segments(job_id)
        shots: list[VisualShot] | None = None

        resolved_mode = self._resolve_analysis_mode(
            segments,
            duration,
            has_speech,
            analysis_mode,
        )

        if resolved_mode == "visual":
            shots, visual_duration = self._load_visual_timeline(job_id)
            duration = duration or visual_duration
        elif not segments:
            raise AIAnalysisError(
                f"Transcript for job '{job_id}' is empty. Run scene detection first."
            )
        else:
            visual_data = self._try_load_visual_timeline(job_id)
            if visual_data is not None:
                shots, visual_duration = visual_data
                duration = duration or visual_duration

        # Text-out montage models: transcript + shot timeline (no proxy video upload).
        models = self.settings.resolved_gemini_models
        has_video_capable = any(_model_supports_video(m) for m in models)
        use_video = (
            has_video_capable
            and (self.settings.use_video_for_llm or resolved_mode == "visual")
        )
        if use_video and not proxy_video_path.is_file():
            raise AIAnalysisError(
                f"Proxy video not found for job '{job_id}'. Run media processing first."
            )

        from app.utils.sources_manifest import load_sources_manifest

        manifest = load_sources_manifest(job_dir)
        sources_info = manifest.prompt_block() if manifest is not None else None

        user_prompt = self._build_user_prompt(
            task_prompt=task_prompt,
            analysis_mode=resolved_mode,
            segments=segments,
            shots=shots,
            duration=duration,
            sources_info=sources_info,
        )

        if self.settings.resolved_llm_provider == "deepseek":
            return self._analyze_with_deepseek(
                job_id=job_id,
                user_prompt=user_prompt,
                analysis_mode=resolved_mode,
                duration=duration,
                save=save,
                started_at=started_at,
            )

        try:
            return self._analyze_with_gemini(
                job_id=job_id,
                user_prompt=user_prompt,
                analysis_mode=resolved_mode,
                duration=duration,
                proxy_video_path=proxy_video_path,
                use_video=use_video,
                save=save,
                started_at=started_at,
            )
        except AIAnalysisError as exc:
            if not self.settings.llm_deepseek_fallback_enabled:
                raise
            logger.warning(
                "[analyze] job=%s Gemini unavailable, falling back to DeepSeek: %s",
                job_id,
                exc,
            )
            self.progress.update(
                job_id,
                status="analyzing",
                message="Gemini unavailable, switching to DeepSeek...",
                elapsed_sec=time.monotonic() - started_at,
            )
            return self._analyze_with_deepseek(
                job_id=job_id,
                user_prompt=user_prompt,
                analysis_mode=resolved_mode,
                duration=duration,
                save=save,
                started_at=started_at,
            )

    def _analyze_with_deepseek(
        self,
        *,
        job_id: str,
        user_prompt: str,
        analysis_mode: TimelineSource,
        duration: float | None,
        save: bool,
        started_at: float,
    ) -> EditPlan:
        system_instruction = (
            SYSTEM_INSTRUCTION_VISUAL
            if analysis_mode == "visual"
            else SYSTEM_INSTRUCTION_SPEECH
        )
        system_instruction = f"{system_instruction}\n\n{_edit_plan_schema_hint()}"
        model = self.settings.deepseek_model
        max_attempts = self.settings.gemini_max_retries

        logger.info(
            "[analyze] job=%s provider=deepseek model=%s (text-only, no video)",
            job_id,
            model,
        )

        last_error = "Unknown error"
        last_response = ""

        for attempt in range(1, max_attempts + 1):
            prompt_text = user_prompt
            if attempt > 1:
                prompt_text = self._build_correction_prompt(last_error, last_response)

            self.progress.update(
                job_id,
                status="analyzing",
                attempt=attempt,
                model=model,
                message=f"DeepSeek analyzing text ({model}, attempt {attempt})...",
                elapsed_sec=time.monotonic() - started_at,
            )

            try:
                raw_text = chat_completion_json(
                    system=system_instruction,
                    user=prompt_text,
                    settings=self.settings,
                    model=model,
                )
                plan = EditPlan.model_validate_json(self._extract_json_text(raw_text))
                plan = self._finalize_edit_plan(plan, duration)
                if save:
                    self._save_edit_plan(job_id, plan)

                elapsed = round(time.monotonic() - started_at, 1)
                self.progress.update(
                    job_id,
                    status="completed",
                    attempt=attempt,
                    model=model,
                    clips_count=len(plan.clips),
                    markers_count=len(plan.markers),
                    elapsed_sec=elapsed,
                    message=(
                        f"Done (DeepSeek {model}): {len(plan.clips)} clips, "
                        f"{len(plan.markers)} markers in {elapsed:.1f} s"
                    ),
                )
                logger.info(
                    "[analyze] job=%s completed provider=deepseek model=%s clips=%d markers=%d",
                    job_id,
                    model,
                    len(plan.clips),
                    len(plan.markers),
                )
                return plan
            except (DeepSeekClientError, Exception) as exc:
                last_error = str(exc)
                last_response = locals().get("raw_text", "")
                logger.warning(
                    "[analyze] job=%s deepseek attempt=%d failed: %s",
                    job_id,
                    attempt,
                    last_error,
                )
                if attempt >= max_attempts:
                    raise AIAnalysisError(
                        f"DeepSeek analysis failed after {max_attempts} attempts: {last_error}"
                    ) from exc

        raise AIAnalysisError("DeepSeek analysis failed.")

    def _analyze_with_gemini(
        self,
        *,
        job_id: str,
        user_prompt: str,
        analysis_mode: TimelineSource,
        duration: float | None,
        proxy_video_path: Path,
        use_video: bool,
        save: bool,
        started_at: float,
    ) -> EditPlan:
        try:
            client = create_gemini_client(self.settings)
        except GeminiClientError as exc:
            raise AIAnalysisError(str(exc)) from exc

        uploaded_video: types.File | None = None
        try:
            if use_video:
                uploaded_video = self._upload_proxy_video(
                    client,
                    proxy_video_path,
                    job_id=job_id,
                    started_at=started_at,
                )
            else:
                logger.info("[analyze] job=%s text-only mode (transcript + timeline)", job_id)

            models = self.settings.resolved_gemini_models
            max_attempts = self.settings.gemini_max_retries
            model_errors: list[str] = []

            for model_index, model in enumerate(models, start=1):
                validation_attempt = 0
                last_error = "Unknown error"
                last_response = ""

                while validation_attempt < max_attempts:
                    validation_attempt += 1
                    prompt_text = user_prompt
                    if validation_attempt > 1:
                        prompt_text = self._build_correction_prompt(last_error, last_response)

                    raw_text = ""
                    try:
                        video_for_model = (
                            uploaded_video
                            if uploaded_video is not None and _model_supports_video(model)
                            else None
                        )
                        if uploaded_video is not None and video_for_model is None:
                            logger.info(
                                "[analyze] job=%s model=%s skipping video input (text-only)",
                                job_id,
                                model,
                            )
                        plan, raw_text = self._generate_edit_plan(
                            client,
                            video_file=video_for_model,
                            prompt_text=prompt_text,
                            analysis_mode=analysis_mode,
                            model=model,
                            attempt=validation_attempt,
                            job_id=job_id,
                            started_at=started_at,
                        )
                        plan = self._finalize_edit_plan(plan, duration)
                        if save:
                            self._save_edit_plan(job_id, plan)

                        elapsed = round(time.monotonic() - started_at, 1)
                        self.progress.update(
                            job_id,
                            status="completed",
                            attempt=validation_attempt,
                            model=model,
                            clips_count=len(plan.clips),
                            markers_count=len(plan.markers),
                            elapsed_sec=elapsed,
                            message=(
                                f"Done ({model}): {len(plan.clips)} clips, "
                                f"{len(plan.markers)} markers in {elapsed:.1f} s"
                            ),
                        )
                        logger.info(
                            "[analyze] job=%s completed model=%s clips=%d markers=%d elapsed=%.1fs",
                            job_id,
                            model,
                            len(plan.clips),
                            len(plan.markers),
                            elapsed,
                        )
                        return plan
                    except Exception as exc:
                        if (
                            uploaded_video is not None
                            and video_for_model is not None
                            and _is_video_input_error(exc)
                        ):
                            logger.warning(
                                "[analyze] job=%s model=%s video rejected (%s), retry text-only",
                                job_id,
                                model,
                                exc,
                            )
                            try:
                                plan, raw_text = self._generate_edit_plan(
                                    client,
                                    video_file=None,
                                    prompt_text=prompt_text,
                                    analysis_mode=analysis_mode,
                                    model=model,
                                    attempt=validation_attempt,
                                    job_id=job_id,
                                    started_at=started_at,
                                )
                                plan = self._finalize_edit_plan(plan, duration)
                                if save:
                                    self._save_edit_plan(job_id, plan)
                                elapsed = round(time.monotonic() - started_at, 1)
                                self.progress.update(
                                    job_id,
                                    status="completed",
                                    attempt=validation_attempt,
                                    model=model,
                                    clips_count=len(plan.clips),
                                    markers_count=len(plan.markers),
                                    elapsed_sec=elapsed,
                                    message=(
                                        f"Done ({model}, text): {len(plan.clips)} clips, "
                                        f"{len(plan.markers)} markers in {elapsed:.1f} s"
                                    ),
                                )
                                return plan
                            except Exception as retry_exc:
                                exc = retry_exc

                        if _is_transient_error(exc) and validation_attempt < max_attempts:
                            wait_sec = _transient_wait_sec(
                                self.settings,
                                validation_attempt,
                            )
                            logger.info(
                                "[analyze] job=%s model=%s transient error, wait %.0fs (attempt %d/%d)",
                                job_id,
                                model,
                                wait_sec,
                                validation_attempt,
                                max_attempts,
                            )
                            self.progress.update(
                                job_id,
                                status="analyzing",
                                model=model,
                                message=(
                                    f"API overloaded ({model}), pausing {wait_sec:.0f} s "
                                    f"(attempt {validation_attempt}/{max_attempts})..."
                                ),
                                elapsed_sec=time.monotonic() - started_at,
                            )
                            time.sleep(wait_sec)
                            continue

                        if _should_switch_model(exc):
                            friendly = _format_gemini_error(exc, model)
                            model_errors.append(f"{model}: {friendly}")
                            logger.warning(
                                "[analyze] job=%s model=%s unavailable (%s), switching model",
                                job_id,
                                model,
                                friendly,
                            )
                            if model_index < len(models):
                                next_model = models[model_index]
                                self.progress.update(
                                    job_id,
                                    status="analyzing",
                                    model=next_model,
                                    message=(
                                        f"Model {model} unavailable, "
                                        f"switching to {next_model}..."
                                    ),
                                    elapsed_sec=time.monotonic() - started_at,
                                )
                            break

                        last_error = str(exc)
                        last_response = raw_text
                        logger.warning(
                            "[analyze] job=%s model=%s attempt=%d failed: %s",
                            job_id,
                            model,
                            validation_attempt,
                            last_error,
                        )
                        if validation_attempt >= max_attempts:
                            model_errors.append(
                                f"{model}: failed after {max_attempts} attempts: {last_error}"
                            )
                            break

            if model_errors:
                raise AIAnalysisError(
                    "Gemini analysis failed for all models. "
                    + " | ".join(model_errors)
                )
            raise AIAnalysisError("Gemini analysis failed.")
        except AIAnalysisError:
            raise
        except Exception as exc:
            raise AIAnalysisError(f"Gemini analysis failed: {exc}") from exc
        finally:
            if uploaded_video is not None:
                try:
                    client.files.delete(name=uploaded_video.name)
                except Exception:
                    logger.warning(
                        "[analyze] job=%s failed to delete uploaded Gemini file",
                        job_id,
                        exc_info=True,
                    )
