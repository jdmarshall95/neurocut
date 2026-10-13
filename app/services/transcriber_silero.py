from __future__ import annotations

import importlib.util
import logging
import time
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, get_settings
from app.services.transcriber import (
    TranscriptionError,
    TranscriptionResult,
    TranscriptSegment,
    TranscriptSegmentDict,
    read_transcript_json,
    write_transcript_json,
)
from app.services.transcription_progress import TranscriptionProgressTracker

logger = logging.getLogger(__name__)

SILERO_SAMPLE_RATE = 16000
SILERO_MODELS_REPO = "snakers4/silero-models"
SILERO_VAD_REPO = "snakers4/silero-vad"

# Silero STT languages in models.yml (limited locale set).
SILERO_STT_LANGUAGES = frozenset({"en", "de", "es", "ua"})


def silero_is_available() -> bool:
    """True when torch is importable (Silero pulls models via torch.hub)."""
    return importlib.util.find_spec("torch") is not None


@lru_cache
def _load_silero_stt(language: str, device: str):
    import torch

    torch_device = torch.device(device)
    logger.info("Loading Silero STT model (language=%s, device=%s)", language, device)
    model, decoder, utils = torch.hub.load(
        repo_or_dir=SILERO_MODELS_REPO,
        model="silero_stt",
        language=language,
        device=torch_device,
        trust_repo=True,
    )
    return model, decoder, utils, torch_device


@lru_cache
def _load_silero_vad():
    import torch

    logger.info("Loading Silero VAD model")
    model, utils = torch.hub.load(
        repo_or_dir=SILERO_VAD_REPO,
        model="silero_vad",
        trust_repo=True,
    )
    return model, utils


class SileroTranscriber:
    """Silero-based STT engine (Phase 13).

    Implements the same interface as ``Transcriber`` so it is a drop-in
    replacement inside ``STTService``. Uses Silero VAD to segment speech and
    Silero STT to transcribe each chunk, producing timestamped segments.
    """

    engine_name = "silero"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.progress = TranscriptionProgressTracker(self.settings)

    def _resolve_language(self) -> str:
        language = (
            self.settings.whisper_language
            or self.settings.silero_language
            or "en"
        ).lower()
        if language not in SILERO_STT_LANGUAGES:
            raise TranscriptionError(
                f"Silero STT does not support language '{language}'. "
                f"Available: {', '.join(sorted(SILERO_STT_LANGUAGES))}. "
                "Use STT_ENGINE=whisper for this language or other unsupported locales."
            )
        return language

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

        if not silero_is_available():
            raise TranscriptionError(
                "Silero STT requires the 'torch' package. "
                "Install it via 'pip install -r requirements-silero.txt'."
            )

        started_at = time.monotonic()
        language = self._resolve_language()
        device = self.settings.silero_device or "cpu"
        model_label = f"silero_stt:{language}"

        if job_id is not None:
            self.progress.start(
                job_id,
                model=model_label,
                device=device,
                compute_type="fp32",
                message="Loading Silero models (may take up to a minute)...",
            )

        logger.info(
            "[silero] job=%s audio=%s language=%s device=%s",
            job_id or "-",
            source,
            language,
            device,
        )

        try:
            segments, duration = self._run(
                source,
                language=language,
                device=device,
                job_id=job_id,
                started_at=started_at,
            )
        except TranscriptionError:
            if job_id is not None:
                self.progress.fail(job_id, "Silero transcription failed.")
            raise
        except Exception as exc:
            if job_id is not None:
                self.progress.fail(job_id, str(exc))
            raise TranscriptionError(
                f"Failed to transcribe '{source}' with Silero: {exc}"
            ) from exc

        elapsed_sec = round(time.monotonic() - started_at, 1)

        if not segments:
            if allow_silent:
                result = TranscriptionResult(
                    segments=[],
                    language=language,
                    duration=round(duration, 3) or None,
                    elapsed_sec=elapsed_sec,
                    device=device,
                    compute_type="fp32",
                )
                if save and job_id is not None:
                    write_transcript_json(self.settings, result, job_id, has_speech=False)
                if job_id is not None:
                    self.progress.update(
                        job_id,
                        status="completed",
                        segment_count=0,
                        progress_percent=100.0,
                        processed_until_sec=result.duration or 0.0,
                        elapsed_sec=elapsed_sec,
                        message="No speech detected; visual analysis will be used.",
                    )
                logger.info(
                    "[silero] job=%s completed with no speech segments", job_id or "-"
                )
                return result

            message = f"Silero produced no speech segments for '{source}'."
            if job_id is not None:
                self.progress.fail(job_id, message)
            raise TranscriptionError(message)

        result = TranscriptionResult(
            segments=segments,
            language=language,
            duration=round(duration, 3) or None,
            elapsed_sec=elapsed_sec,
            device=device,
            compute_type="fp32",
        )

        if save and job_id is not None:
            write_transcript_json(self.settings, result, job_id, has_speech=True)

        if job_id is not None:
            self.progress.update(
                job_id,
                status="completed",
                segment_count=len(segments),
                progress_percent=100.0,
                processed_until_sec=result.duration or 0.0,
                elapsed_sec=elapsed_sec,
                message=f"Done (Silero): {len(segments)} segments in {elapsed_sec:.1f} s",
            )

        logger.info(
            "[silero] job=%s completed segments=%d language=%s elapsed=%.1fs",
            job_id or "-",
            len(segments),
            language,
            elapsed_sec,
        )
        return result

    def _run(
        self,
        source: Path,
        *,
        language: str,
        device: str,
        job_id: str | None,
        started_at: float,
    ) -> tuple[list[TranscriptSegment], float]:
        import torch

        stt_model, decoder, utils, torch_device = _load_silero_stt(language, device)
        read_batch, split_into_batches, read_audio, prepare_model_input = utils
        vad_model, vad_utils = _load_silero_vad()
        get_speech_timestamps = vad_utils[0]

        if job_id is not None:
            self.progress.update(
                job_id,
                status="loading_model",
                message="Models loaded, speech detection (VAD)...",
                elapsed_sec=time.monotonic() - started_at,
            )

        wav = read_audio(str(source), sampling_rate=SILERO_SAMPLE_RATE)
        duration = float(wav.shape[-1]) / SILERO_SAMPLE_RATE

        if job_id is not None and duration > 0:
            self.progress.update(
                job_id,
                audio_duration_sec=duration,
                message=f"Audio: {duration:.1f} s",
            )

        speech_ts = get_speech_timestamps(
            wav, vad_model, sampling_rate=SILERO_SAMPLE_RATE
        )

        segments: list[TranscriptSegment] = []
        for chunk_ts in speech_ts:
            start_sample = int(chunk_ts["start"])
            end_sample = int(chunk_ts["end"])
            start = start_sample / SILERO_SAMPLE_RATE
            end = end_sample / SILERO_SAMPLE_RATE
            if end <= start:
                continue

            chunk = wav[start_sample:end_sample]
            model_input = prepare_model_input([chunk], device=torch_device)
            with torch.no_grad():
                output = stt_model(model_input)
            text = decoder(output[0].cpu()).strip()
            if not text:
                continue

            segments.append(
                TranscriptSegment(
                    start=round(start, 3),
                    end=round(end, 3),
                    text=text,
                )
            )

            if job_id is not None:
                segment_count = len(segments)
                elapsed = time.monotonic() - started_at
                progress_percent = (
                    min(100.0, (end / duration) * 100.0) if duration > 0 else 0.0
                )
                preview = text if len(text) <= 80 else f"{text[:77]}..."
                self.progress.update(
                    job_id,
                    status="transcribing",
                    segment_count=segment_count,
                    progress_percent=round(progress_percent, 1),
                    processed_until_sec=round(end, 3),
                    elapsed_sec=round(elapsed, 1),
                    message=f"Segment {segment_count}: {preview}",
                    last_segment_preview=preview,
                )

        return segments, duration

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
            write_transcript_json(self.settings, result, job_id, has_speech=False)
        self.progress.update(
            job_id,
            status="completed",
            model=f"silero_stt:{self.settings.silero_language}",
            device="skipped",
            compute_type="skipped",
            segment_count=0,
            progress_percent=100.0,
            audio_duration_sec=duration,
            processed_until_sec=duration or 0.0,
            elapsed_sec=0.0,
            message="No audio track; visual analysis will be used.",
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
            self.settings, result, job_id, has_speech=has_speech
        )

    def load_transcript(self, job_id: str) -> TranscriptionResult:
        return read_transcript_json(self.settings, job_id)

    def to_dicts(self, result: TranscriptionResult) -> list[TranscriptSegmentDict]:
        return [
            {"start": segment.start, "end": segment.end, "text": segment.text}
            for segment in result.segments
        ]
