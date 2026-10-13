from __future__ import annotations

import importlib.util
import logging
import time
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

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

GIGAAM_SAMPLE_RATE = 16000
GIGAAM_LANGUAGE = "ru"


def sherpa_onnx_is_available() -> bool:
    return importlib.util.find_spec("sherpa_onnx") is not None


def gigaam_is_available(settings: Settings | None = None) -> bool:
    """True when sherpa-onnx is importable and model files are present."""
    if not sherpa_onnx_is_available():
        return False
    settings = settings or get_settings()
    return (
        settings.gigaam_model_path.is_file()
        and settings.gigaam_tokens_path.is_file()
        and settings.gigaam_vad_path.is_file()
    )


@lru_cache
def _load_recognizer(model_path: str, tokens_path: str, num_threads: int):
    import sherpa_onnx

    logger.info("Loading GigaAM NeMo-CTC recognizer (model=%s)", model_path)
    return sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=model_path,
        tokens=tokens_path,
        num_threads=num_threads,
        decoding_method="greedy_search",
    )


def _read_wav_mono_16k(path: Path) -> np.ndarray:
    """Read a 16 kHz mono PCM16 WAV into a normalized float32 array."""
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if sample_width != 2:
        raise TranscriptionError(
            f"GigaAM expects 16-bit PCM WAV, got sample width {sample_width} bytes."
        )

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if sample_rate != GIGAAM_SAMPLE_RATE:
        raise TranscriptionError(
            f"GigaAM expects {GIGAAM_SAMPLE_RATE} Hz audio, got {sample_rate} Hz."
        )
    return samples


class GigaAMTranscriber:
    """Offline GigaAM STT via sherpa-onnx + GigaAM NeMo-CTC (Phase 13).

    Mirrors the ``Transcriber`` interface so it drops into ``STTService``.
    Uses Silero VAD (ONNX) for speech segmentation and GigaAM CTC to decode
    each speech chunk, producing timestamped segments.
    """

    engine_name = "gigaam"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.progress = TranscriptionProgressTracker(self.settings)

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

        if not sherpa_onnx_is_available():
            raise TranscriptionError(
                "GigaAM requires the 'sherpa-onnx' package. "
                "Install it via 'pip install -r requirements-gigaam.txt'."
            )
        if not self.settings.gigaam_model_path.is_file():
            raise TranscriptionError(
                f"GigaAM model not found at {self.settings.gigaam_model_path}. "
                "Download it (see README) or use STT_ENGINE=whisper."
            )
        if not self.settings.gigaam_vad_path.is_file():
            raise TranscriptionError(
                f"Silero VAD model not found at {self.settings.gigaam_vad_path}."
            )

        started_at = time.monotonic()

        if job_id is not None:
            self.progress.start(
                job_id,
                model="gigaam-ru",
                device="cpu",
                compute_type="int8",
                message="Loading GigaAM model...",
            )

        logger.info("[gigaam] job=%s audio=%s", job_id or "-", source)

        try:
            segments, duration = self._run(
                source, job_id=job_id, started_at=started_at
            )
        except TranscriptionError:
            if job_id is not None:
                self.progress.fail(job_id, "GigaAM transcription failed.")
            raise
        except Exception as exc:
            if job_id is not None:
                self.progress.fail(job_id, str(exc))
            raise TranscriptionError(
                f"Failed to transcribe '{source}' with GigaAM: {exc}"
            ) from exc

        elapsed_sec = round(time.monotonic() - started_at, 1)

        if not segments:
            if allow_silent:
                result = TranscriptionResult(
                    segments=[],
                    language=GIGAAM_LANGUAGE,
                    duration=round(duration, 3) or None,
                    elapsed_sec=elapsed_sec,
                    device="cpu",
                    compute_type="int8",
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
                    "[gigaam] job=%s completed with no speech segments", job_id or "-"
                )
                return result

            message = f"GigaAM produced no speech segments for '{source}'."
            if job_id is not None:
                self.progress.fail(job_id, message)
            raise TranscriptionError(message)

        result = TranscriptionResult(
            segments=segments,
            language=GIGAAM_LANGUAGE,
            duration=round(duration, 3) or None,
            elapsed_sec=elapsed_sec,
            device="cpu",
            compute_type="int8",
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
                message=f"Done (GigaAM): {len(segments)} segments in {elapsed_sec:.1f} s",
            )

        logger.info(
            "[gigaam] job=%s completed segments=%d elapsed=%.1fs",
            job_id or "-",
            len(segments),
            elapsed_sec,
        )
        return result

    def _run(
        self,
        source: Path,
        *,
        job_id: str | None,
        started_at: float,
    ) -> tuple[list[TranscriptSegment], float]:
        import sherpa_onnx

        recognizer = _load_recognizer(
            str(self.settings.gigaam_model_path),
            str(self.settings.gigaam_tokens_path),
            self.settings.gigaam_num_threads,
        )

        if job_id is not None:
            self.progress.update(
                job_id,
                status="loading_model",
                message="Model loaded, speech detection (VAD)...",
                elapsed_sec=time.monotonic() - started_at,
            )

        samples = _read_wav_mono_16k(source)
        duration = float(len(samples)) / GIGAAM_SAMPLE_RATE

        if job_id is not None and duration > 0:
            self.progress.update(
                job_id,
                audio_duration_sec=duration,
                message=f"Audio: {duration:.1f} s",
            )

        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = str(self.settings.gigaam_vad_path)
        vad_config.silero_vad.threshold = 0.5
        vad_config.silero_vad.min_silence_duration = 0.25
        vad_config.silero_vad.min_speech_duration = 0.25
        vad_config.silero_vad.max_speech_duration = self.settings.gigaam_max_segment_sec
        vad_config.sample_rate = GIGAAM_SAMPLE_RATE

        window_size = vad_config.silero_vad.window_size
        vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=100)

        segments: list[TranscriptSegment] = []

        offset = 0
        while offset + window_size <= len(samples):
            vad.accept_waveform(samples[offset : offset + window_size])
            offset += window_size
            self._drain_vad(vad, recognizer, segments, duration, job_id, started_at)
        vad.flush()
        self._drain_vad(vad, recognizer, segments, duration, job_id, started_at)

        return segments, duration

    def _drain_vad(
        self,
        vad,
        recognizer,
        segments: list[TranscriptSegment],
        duration: float,
        job_id: str | None,
        started_at: float,
    ) -> None:
        while not vad.empty():
            chunk = vad.front
            start = chunk.start / GIGAAM_SAMPLE_RATE
            chunk_samples = chunk.samples
            end = start + len(chunk_samples) / GIGAAM_SAMPLE_RATE

            stream = recognizer.create_stream()
            stream.accept_waveform(GIGAAM_SAMPLE_RATE, chunk_samples)
            recognizer.decode_stream(stream)
            text = stream.result.text.strip()

            vad.pop()

            if not text or end <= start:
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
            model="gigaam-ru",
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
