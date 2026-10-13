from __future__ import annotations

import ctypes
import ctypes.util
import json
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from faster_whisper import WhisperModel
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.services.transcription_progress import TranscriptionProgressTracker

logger = logging.getLogger(__name__)


class TranscriptSegmentDict(TypedDict):
    start: float
    end: float
    text: str


class TranscriptSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1)


class TranscriptionResult(BaseModel):
    segments: list[TranscriptSegment]
    language: str | None = None
    duration: float | None = None
    elapsed_sec: float | None = None
    device: str | None = None
    compute_type: str | None = None


class TranscriptionError(Exception):
    """Raised when faster-whisper transcription fails."""


def write_transcript_json(
    settings: Settings,
    result: TranscriptionResult,
    job_id: str,
    *,
    has_speech: bool | None = None,
    source: str = "speech",
) -> Path:
    """Persist a transcript to ``storage/{job_id}/transcript.json`` (engine-agnostic)."""
    job_dir = (settings.storage_path / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    output_path = job_dir / "transcript.json"

    payload = {
        "source": source,
        "has_speech": has_speech if has_speech is not None else bool(result.segments),
        "language": result.language,
        "duration": result.duration,
        "elapsed_sec": result.elapsed_sec,
        "device": result.device,
        "compute_type": result.compute_type,
        "segments": [segment.model_dump() for segment in result.segments],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def read_transcript_json(settings: Settings, job_id: str) -> TranscriptionResult:
    transcript_path = (settings.storage_path / job_id / "transcript.json").resolve()
    if not transcript_path.is_file():
        raise TranscriptionError(f"Transcript not found for job '{job_id}'.")
    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = [
        TranscriptSegment(**segment) for segment in payload.get("segments", [])
    ]
    return TranscriptionResult(
        segments=segments,
        language=payload.get("language"),
        duration=payload.get("duration"),
        elapsed_sec=payload.get("elapsed_sec"),
        device=payload.get("device"),
        compute_type=payload.get("compute_type"),
    )


def _cuda_is_usable() -> bool:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() == 0:
            return False

        supported = ctranslate2.get_supported_compute_types("cuda")
        if not supported:
            return False

        cublas = ctypes.util.find_library("cublas")
        if cublas:
            ctypes.CDLL(cublas)
            return True

        for lib_name in ("libcublas.so.12", "libcublas.so.11", "libcublas.so"):
            try:
                ctypes.CDLL(lib_name)
                return True
            except OSError:
                continue
    except Exception:
        return False

    return False


def _is_cuda_runtime_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = ("cublas", "cudnn", "cuda", "cudart", "gpu")
    return any(marker in message for marker in markers)


def _resolve_device(device: str) -> str:
    if device == "auto":
        return "cuda" if _cuda_is_usable() else "cpu"

    if device == "cuda" and not _cuda_is_usable():
        logger.warning(
            "CUDA requested but runtime libraries are unavailable. Falling back to CPU."
        )
        return "cpu"

    return device


def _pick_compute_type(device: str, compute_type: str) -> str:
    try:
        import ctranslate2

        supported = set(ctranslate2.get_supported_compute_types(device))
    except Exception:
        supported = {"int8"} if device == "cpu" else set()

    if compute_type != "default" and compute_type in supported:
        return compute_type

    candidates = (
        ["float16", "int8_float16", "int8", "float32"]
        if device == "cuda"
        else ["int8", "int8_float32", "float32", "int16"]
    )
    for candidate in candidates:
        if candidate in supported:
            return candidate

    if supported:
        return sorted(supported)[0]

    return "int8"


@lru_cache
def _load_whisper_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    resolved_device = _resolve_device(device)
    resolved_compute = _pick_compute_type(resolved_device, compute_type)

    logger.info(
        "Loading Whisper model '%s' (device=%s, compute_type=%s)",
        model_size,
        resolved_device,
        resolved_compute,
    )

    try:
        return WhisperModel(
            model_size,
            device=resolved_device,
            compute_type=resolved_compute,
        )
    except ValueError as exc:
        if resolved_device != "cuda":
            raise

        try:
            import ctranslate2

            supported = list(ctranslate2.get_supported_compute_types("cuda"))
        except Exception:
            supported = []

        for fallback_compute in supported:
            if fallback_compute == resolved_compute:
                continue
            try:
                logger.warning(
                    "Retrying Whisper load on CUDA with compute_type=%s",
                    fallback_compute,
                )
                return WhisperModel(
                    model_size,
                    device="cuda",
                    compute_type=fallback_compute,
                )
            except ValueError:
                continue

        cpu_compute = _pick_compute_type("cpu", "default")
        logger.warning("Falling back to CPU with compute_type=%s", cpu_compute)
        try:
            return WhisperModel(
                model_size,
                device="cpu",
                compute_type=cpu_compute,
            )
        except ValueError:
            raise exc


class Transcriber:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.progress = TranscriptionProgressTracker(self.settings)

    def _resolved_runtime(self, device: str, compute_type: str) -> tuple[str, str]:
        resolved_device = _resolve_device(device)
        resolved_compute = _pick_compute_type(resolved_device, compute_type)
        return resolved_device, resolved_compute

    def _update_progress(
        self,
        job_id: str | None,
        *,
        status: str | None = None,
        segment_count: int | None = None,
        progress_percent: float | None = None,
        audio_duration_sec: float | None = None,
        processed_until_sec: float | None = None,
        elapsed_sec: float | None = None,
        message: str | None = None,
        last_segment_preview: str | None = None,
        model: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        error: str | None = None,
    ) -> None:
        if job_id is None:
            return

        fields: dict[str, object] = {}
        if status is not None:
            fields["status"] = status
        if segment_count is not None:
            fields["segment_count"] = segment_count
        if progress_percent is not None:
            fields["progress_percent"] = round(progress_percent, 1)
        if audio_duration_sec is not None:
            fields["audio_duration_sec"] = round(audio_duration_sec, 3)
        if processed_until_sec is not None:
            fields["processed_until_sec"] = round(processed_until_sec, 3)
        if elapsed_sec is not None:
            fields["elapsed_sec"] = round(elapsed_sec, 1)
        if message is not None:
            fields["message"] = message
        if last_segment_preview is not None:
            fields["last_segment_preview"] = last_segment_preview
        if model is not None:
            fields["model"] = model
        if device is not None:
            fields["device"] = device
        if compute_type is not None:
            fields["compute_type"] = compute_type
        if error is not None:
            fields["error"] = error

        if fields:
            self.progress.update(job_id, **fields)

    def _transcribe_with_model(
        self,
        model: WhisperModel,
        source: Path,
        *,
        job_id: str | None,
        started_at: float,
        resolved_device: str,
        resolved_compute: str,
    ) -> tuple[list[TranscriptSegment], object]:
        logger.info("Starting transcription for %s", source)
        self._update_progress(
            job_id,
            status="transcribing",
            message="Starting speech recognition...",
            device=resolved_device,
            compute_type=resolved_compute,
            elapsed_sec=time.monotonic() - started_at,
        )

        segments_iter, info = model.transcribe(
            str(source),
            language=self.settings.whisper_language,
            word_timestamps=False,
            vad_filter=self.settings.whisper_vad_filter,
        )

        audio_duration = float(getattr(info, "duration", 0.0) or 0.0)
        if audio_duration > 0:
            self._update_progress(
                job_id,
                audio_duration_sec=audio_duration,
                message=f"Audio: {audio_duration:.1f} s",
            )
            logger.info("Audio duration: %.1f sec", audio_duration)

        segments: list[TranscriptSegment] = []
        for segment in segments_iter:
            text = segment.text.strip()
            if not text:
                continue

            segments.append(
                TranscriptSegment(
                    start=round(segment.start, 3),
                    end=round(segment.end, 3),
                    text=text,
                )
            )

            segment_count = len(segments)
            elapsed = time.monotonic() - started_at
            progress_percent = (
                min(100.0, (segment.end / audio_duration) * 100.0)
                if audio_duration > 0
                else 0.0
            )
            preview = text if len(text) <= 80 else f"{text[:77]}..."

            self._update_progress(
                job_id,
                status="transcribing",
                segment_count=segment_count,
                progress_percent=progress_percent,
                processed_until_sec=segment.end,
                elapsed_sec=elapsed,
                message=f"Segment {segment_count}: {preview}",
                last_segment_preview=preview,
            )

            if (
                segment_count == 1
                or segment_count % self.settings.whisper_log_every_n_segments == 0
            ):
                logger.info(
                    "[transcribe] job=%s segment=%d progress=%.1f%% time=%.1f/%.1fs elapsed=%.1fs text=%r",
                    job_id or "-",
                    segment_count,
                    progress_percent,
                    segment.end,
                    audio_duration,
                    elapsed,
                    preview,
                )

        return segments, info

    def record_no_audio(
        self,
        *,
        job_id: str,
        duration: float | None = None,
        save: bool = True,
    ) -> TranscriptionResult:
        result = TranscriptionResult(
            segments=[],
            language=None,
            duration=round(duration, 3) if duration is not None else None,
            elapsed_sec=0.0,
            device=None,
            compute_type=None,
        )

        if save:
            self.save_transcript(result, job_id, has_speech=False)

        self.progress.update(
            job_id,
            status="completed",
            model=self.settings.whisper_model,
            device="skipped",
            compute_type="skipped",
            segment_count=0,
            progress_percent=100.0,
            audio_duration_sec=duration,
            processed_until_sec=duration or 0.0,
            elapsed_sec=0.0,
            message="No audio track; visual analysis will be used.",
        )
        logger.info("[transcribe] job=%s skipped: source video has no audio track", job_id)
        return result

    def transcribe(
        self,
        audio_path: Path,
        *,
        job_id: str | None = None,
        save: bool = True,
        allow_silent: bool = False,
    ) -> TranscriptionResult:
        source = Path(audio_path).resolve()
        if not source.is_file():
            raise TranscriptionError(f"Audio file not found: {source}")

        started_at = time.monotonic()
        device = self.settings.whisper_device
        compute_type = self.settings.whisper_compute_type
        resolved_device, resolved_compute = self._resolved_runtime(device, compute_type)

        if job_id is not None:
            self.progress.start(
                job_id,
                model=self.settings.whisper_model,
                device=resolved_device,
                compute_type=resolved_compute,
                message="Loading Whisper model (may take up to a minute)...",
            )

        logger.info(
            "[transcribe] job=%s audio=%s model=%s device=%s compute=%s language=%s",
            job_id or "-",
            source,
            self.settings.whisper_model,
            resolved_device,
            resolved_compute,
            self.settings.whisper_language or "auto",
        )

        try:
            model = _load_whisper_model(
                self.settings.whisper_model,
                device,
                compute_type,
            )
            self._update_progress(
                job_id,
                status="loading_model",
                message="Model loaded, recognizing speech...",
                elapsed_sec=time.monotonic() - started_at,
            )
            segments, info = self._transcribe_with_model(
                model,
                source,
                job_id=job_id,
                started_at=started_at,
                resolved_device=resolved_device,
                resolved_compute=resolved_compute,
            )
        except TranscriptionError:
            if job_id is not None:
                self.progress.fail(job_id, "Transcription failed.")
            raise
        except Exception as exc:
            if device == "cpu" or not _is_cuda_runtime_error(exc):
                if job_id is not None:
                    self.progress.fail(job_id, str(exc))
                raise TranscriptionError(
                    f"Failed to transcribe '{source}': {exc}"
                ) from exc

            logger.warning(
                "CUDA transcription failed (%s). Retrying on CPU.",
                exc,
            )
            _load_whisper_model.cache_clear()
            resolved_device, resolved_compute = self._resolved_runtime("cpu", compute_type)
            self._update_progress(
                job_id,
                status="loading_model",
                device=resolved_device,
                compute_type=resolved_compute,
                message="CUDA unavailable, retrying on CPU...",
            )
            try:
                model = _load_whisper_model(
                    self.settings.whisper_model,
                    "cpu",
                    compute_type,
                )
                segments, info = self._transcribe_with_model(
                    model,
                    source,
                    job_id=job_id,
                    started_at=started_at,
                    resolved_device=resolved_device,
                    resolved_compute=resolved_compute,
                )
            except Exception as retry_exc:
                if job_id is not None:
                    self.progress.fail(job_id, str(retry_exc))
                raise TranscriptionError(
                    f"Failed to transcribe '{source}': {retry_exc}"
                ) from retry_exc

        if not segments:
            if allow_silent:
                elapsed_sec = round(time.monotonic() - started_at, 1)
                result = TranscriptionResult(
                    segments=[],
                    language=getattr(info, "language", None),
                    duration=round(getattr(info, "duration", 0.0) or 0.0, 3) or None,
                    elapsed_sec=elapsed_sec,
                    device=resolved_device,
                    compute_type=resolved_compute,
                )
                if save and job_id is not None:
                    self.save_transcript(result, job_id, has_speech=False)
                if job_id is not None:
                    self._update_progress(
                        job_id,
                        status="completed",
                        segment_count=0,
                        progress_percent=100.0,
                        processed_until_sec=result.duration or 0.0,
                        elapsed_sec=elapsed_sec,
                        message="No speech detected; visual analysis will be used.",
                    )
                logger.info(
                    "[transcribe] job=%s completed with no speech segments (silent video)",
                    job_id or "-",
                )
                return result

            message = f"Transcription produced no speech segments for '{source}'."
            if job_id is not None:
                self.progress.fail(job_id, message)
            raise TranscriptionError(message)

        elapsed_sec = round(time.monotonic() - started_at, 1)
        result = TranscriptionResult(
            segments=segments,
            language=getattr(info, "language", None),
            duration=round(getattr(info, "duration", 0.0) or 0.0, 3) or None,
            elapsed_sec=elapsed_sec,
            device=resolved_device,
            compute_type=resolved_compute,
        )

        if save and job_id is not None:
            self.save_transcript(result, job_id, has_speech=True)

        if job_id is not None:
            self._update_progress(
                job_id,
                status="completed",
                segment_count=len(segments),
                progress_percent=100.0,
                processed_until_sec=result.duration or 0.0,
                elapsed_sec=elapsed_sec,
                message=f"Done: {len(segments)} segments in {elapsed_sec:.1f} s",
            )

        logger.info(
            "[transcribe] job=%s completed segments=%d language=%s elapsed=%.1fs",
            job_id or "-",
            len(segments),
            result.language,
            elapsed_sec,
        )

        return result

    def save_transcript(
        self,
        result: TranscriptionResult,
        job_id: str,
        *,
        has_speech: bool | None = None,
    ) -> Path:
        return write_transcript_json(
            self.settings,
            result,
            job_id,
            has_speech=has_speech,
        )

    def load_transcript(self, job_id: str) -> TranscriptionResult:
        return read_transcript_json(self.settings, job_id)

    def to_dicts(self, result: TranscriptionResult) -> list[TranscriptSegmentDict]:
        return [
            {"start": segment.start, "end": segment.end, "text": segment.text}
            for segment in result.segments
        ]
