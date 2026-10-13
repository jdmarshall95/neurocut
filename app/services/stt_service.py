from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import ffmpeg

from app.core.config import Settings, get_settings
from app.core.metrics import observe_stage
from app.services.transcriber import (
    Transcriber,
    TranscriptionError,
    TranscriptionResult,
    TranscriptSegment,
)
from app.services.transcriber_gigaam import GigaAMTranscriber, gigaam_is_available
from app.services.transcriber_silero import (
    SILERO_STT_LANGUAGES,
    SileroTranscriber,
    silero_is_available,
)
from app.services.transcription_progress import TranscriptionProgressTracker

logger = logging.getLogger(__name__)

HASH_SAMPLE_BYTES = 1024 * 1024  # first 1 MB of the audio file


class STTServiceError(Exception):
    """Raised when the STT service cannot produce a transcript."""


@dataclass(frozen=True)
class STTOptions:
    language: str | None = None
    allow_silent: bool = True
    use_cache: bool = True


class Transcript(TranscriptionResult):
    """Transcript enriched with STT-service metadata."""

    source: str = "speech"
    has_speech: bool = True
    file_hash: str | None = None
    cached: bool = False
    engine: str = "whisper"


class STTService:
    """Standalone, cache-backed speech-to-text service (Phase 12).

    Decouples transcription from the LLM pipeline so transcripts can be
    reused across jobs, uploaded by users, or swapped for another engine.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.transcriber = Transcriber(self.settings)
        self._silero: SileroTranscriber | None = None
        self._gigaam: GigaAMTranscriber | None = None
        self.progress = TranscriptionProgressTracker(self.settings)

    def _resolve_engine(self, language: str | None) -> str:
        """Pick the STT engine per config (whisper | silero | gigaam | auto)."""
        requested = (self.settings.stt_engine or "whisper").lower()
        hint = (language or self.settings.whisper_language or "").lower()
        # Locale codes that prefer GigaAM when STT_ENGINE=auto.
        prefer_gigaam = hint in {"ru"}

        if requested == "auto":
            if prefer_gigaam and gigaam_is_available(self.settings):
                return "gigaam"
            if hint in SILERO_STT_LANGUAGES and silero_is_available():
                return "silero"
            return "whisper"

        engine = requested

        if engine == "gigaam":
            if not gigaam_is_available(self.settings):
                logger.warning(
                    "[stt] GigaAM requested but sherpa-onnx or model files are "
                    "missing; falling back to Whisper."
                )
                return "whisper"

        if engine == "silero":
            silero_lang = (hint or self.settings.silero_language or "en").lower()
            if silero_lang not in SILERO_STT_LANGUAGES:
                logger.warning(
                    "[stt] Silero STT does not support '%s' (only %s); using Whisper.",
                    silero_lang,
                    ", ".join(sorted(SILERO_STT_LANGUAGES)),
                )
                return "whisper"
            if not silero_is_available():
                logger.warning(
                    "[stt] Silero requested but 'torch' is not installed; "
                    "falling back to Whisper."
                )
                return "whisper"
        return engine

    def _get_transcriber(self, engine: str):
        if engine == "silero":
            if self._silero is None:
                self._silero = SileroTranscriber(self.settings)
            return self._silero
        if engine == "gigaam":
            if self._gigaam is None:
                self._gigaam = GigaAMTranscriber(self.settings)
            return self._gigaam
        return self.transcriber

    # ------------------------------------------------------------------ #
    # Content-addressable cache
    # ------------------------------------------------------------------ #
    def _cache_path(self, file_hash: str) -> Path:
        return self.settings.transcripts_cache_path / f"{file_hash}.json"

    def _probe_duration(self, audio_path: Path) -> float:
        try:
            probe = ffmpeg.probe(str(audio_path), cmd=self.settings.ffprobe_path)
        except ffmpeg.Error:
            return 0.0
        return float(probe.get("format", {}).get("duration") or 0.0)

    def compute_file_hash(self, audio_path: str | Path) -> str:
        """SHA-256 of the first 1 MB of the file plus its duration."""
        path = Path(audio_path)
        if not path.is_file():
            raise STTServiceError(f"Audio file not found: {path}")

        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            hasher.update(handle.read(HASH_SAMPLE_BYTES))

        duration = self._probe_duration(path)
        hasher.update(f"|dur={duration:.3f}".encode("utf-8"))
        return hasher.hexdigest()

    def get_cached(self, file_hash: str) -> Transcript | None:
        cache_path = self._cache_path(file_hash)
        if not cache_path.is_file():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("[stt] corrupt cache entry ignored: %s", cache_path)
            return None
        payload.setdefault("file_hash", file_hash)
        payload["cached"] = True
        return Transcript.model_validate(payload)

    def _store_cache(self, file_hash: str, transcript: Transcript) -> Path:
        self.settings.ensure_transcripts_cache()
        cache_path = self._cache_path(file_hash)
        payload = transcript.model_dump()
        payload["file_hash"] = file_hash
        payload["cached"] = False
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return cache_path

    # ------------------------------------------------------------------ #
    # Transcript persistence for a job
    # ------------------------------------------------------------------ #
    def _write_job_transcript(self, job_id: str, transcript: Transcript) -> Path:
        job_dir = (self.settings.storage_path / job_id).resolve()
        job_dir.mkdir(parents=True, exist_ok=True)
        output_path = job_dir / "transcript.json"
        payload = {
            "source": transcript.source,
            "has_speech": transcript.has_speech,
            "language": transcript.language,
            "duration": transcript.duration,
            "elapsed_sec": transcript.elapsed_sec,
            "device": transcript.device,
            "compute_type": transcript.compute_type,
            "file_hash": transcript.file_hash,
            "cached": transcript.cached,
            "segments": [segment.model_dump() for segment in transcript.segments],
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    @staticmethod
    def _to_transcript(
        result: TranscriptionResult,
        *,
        file_hash: str | None,
        cached: bool,
        engine: str = "whisper",
    ) -> Transcript:
        return Transcript(
            segments=result.segments,
            language=result.language,
            duration=result.duration,
            elapsed_sec=result.elapsed_sec,
            device=result.device,
            compute_type=result.compute_type,
            source="speech",
            has_speech=bool(result.segments),
            file_hash=file_hash,
            cached=cached,
            engine=engine,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def transcribe(
        self,
        audio_path: str | Path,
        options: STTOptions | None = None,
        *,
        job_id: str | None = None,
    ) -> Transcript:
        opts = options or STTOptions()
        source = Path(audio_path)
        if not source.is_file():
            raise STTServiceError(f"Audio file not found: {source}")

        started = time.perf_counter()
        use_cache = opts.use_cache and self.settings.stt_cache_enabled
        file_hash: str | None = None
        if use_cache:
            file_hash = self.compute_file_hash(source)
            cached = self.get_cached(file_hash)
            if cached is not None:
                logger.info("[stt] cache hit hash=%s", file_hash[:12])
                if job_id is not None:
                    self._write_job_transcript(job_id, cached)
                    self._mark_progress_completed(job_id, cached, from_cache=True)
                observe_stage("transcription", time.perf_counter() - started)
                return cached

        engine = self._resolve_engine(opts.language)
        transcriber = self._get_transcriber(engine)
        logger.info("[stt] engine=%s job=%s", engine, job_id or "-")

        previous_language = self.settings.whisper_language
        try:
            if opts.language is not None:
                self.settings.whisper_language = opts.language
            result = transcriber.transcribe(
                source,
                job_id=job_id,
                save=True,
                allow_silent=opts.allow_silent,
            )
        except TranscriptionError as exc:
            # If an alternative engine fails at runtime, retry once with Whisper.
            if engine != "whisper":
                logger.warning(
                    "[stt] %s failed (%s); retrying with Whisper.", engine, exc
                )
                try:
                    result = self.transcriber.transcribe(
                        source,
                        job_id=job_id,
                        save=True,
                        allow_silent=opts.allow_silent,
                    )
                    engine = "whisper"
                except TranscriptionError as retry_exc:
                    observe_stage("transcription", time.perf_counter() - started)
                    raise STTServiceError(str(retry_exc)) from retry_exc
            else:
                observe_stage("transcription", time.perf_counter() - started)
                raise STTServiceError(str(exc)) from exc
        finally:
            self.settings.whisper_language = previous_language

        transcript = self._to_transcript(
            result,
            file_hash=file_hash,
            cached=False,
            engine=engine,
        )
        if use_cache and file_hash is not None:
            self._store_cache(file_hash, transcript)
        elapsed = time.perf_counter() - started
        observe_stage("transcription", elapsed)
        logger.info(
            "[stt] done job=%s engine=%s segments=%d elapsed=%.2fs cached=false",
            job_id or "-",
            engine,
            len(transcript.segments),
            elapsed,
        )
        return transcript

    def _mark_progress_completed(
        self,
        job_id: str,
        transcript: Transcript,
        *,
        from_cache: bool,
    ) -> None:
        suffix = " (from cache)" if from_cache else ""
        self.progress.update(
            job_id,
            status="completed",
            segment_count=len(transcript.segments),
            progress_percent=100.0,
            audio_duration_sec=transcript.duration,
            processed_until_sec=transcript.duration or 0.0,
            elapsed_sec=transcript.elapsed_sec or 0.0,
            language=transcript.language,
            message=f"Done: {len(transcript.segments)} segments{suffix}",
        )

    # ------------------------------------------------------------------ #
    # User-supplied transcripts (SRT / VTT / JSON)
    # ------------------------------------------------------------------ #
    def parse_transcript_file(self, filename: str, content: bytes) -> Transcript:
        text = content.decode("utf-8", errors="replace")
        suffix = Path(filename).suffix.lower()

        if suffix == ".json" or (not suffix and text.lstrip().startswith(("{", "["))):
            segments = _parse_json_segments(text)
        elif suffix == ".vtt" or text.lstrip().upper().startswith("WEBVTT"):
            segments = _parse_srt_vtt(text, is_vtt=True)
        else:
            segments = _parse_srt_vtt(text, is_vtt=False)

        if not segments:
            raise STTServiceError(
                f"No usable segments parsed from transcript '{filename}'."
            )

        duration = max((segment.end for segment in segments), default=0.0)
        return Transcript(
            segments=segments,
            language=None,
            duration=round(duration, 3) or None,
            elapsed_sec=0.0,
            device="uploaded",
            compute_type="uploaded",
            source="uploaded",
            has_speech=True,
            cached=False,
        )

    def store_uploaded_transcript(
        self,
        transcript: Transcript,
        *,
        job_id: str | None = None,
        file_hash: str | None = None,
    ) -> dict[str, str]:
        written: dict[str, str] = {}
        if file_hash:
            transcript = transcript.model_copy(update={"file_hash": file_hash})
            written["cache_path"] = str(self._store_cache(file_hash, transcript))
        if job_id is not None:
            written["transcript_path"] = str(self._write_job_transcript(job_id, transcript))
            self._mark_progress_completed(job_id, transcript, from_cache=False)
        return written


# ---------------------------------------------------------------------- #
# Parsers
# ---------------------------------------------------------------------- #
_TIMECODE_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})"
)


def _timecode_to_seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    ms = millis.ljust(3, "0")[:3]
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(ms) / 1000.0


def _parse_srt_vtt(text: str, *, is_vtt: bool) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if is_vtt and lines[0].upper().startswith("WEBVTT"):
            lines = lines[1:]
        if not lines:
            continue

        timecode_line = None
        text_start_index = 0
        for index, line in enumerate(lines):
            match = _TIMECODE_RE.search(line)
            if match:
                timecode_line = match
                text_start_index = index + 1
                break
        if timecode_line is None:
            continue

        start = _timecode_to_seconds(*timecode_line.group(1, 2, 3, 4))
        end = _timecode_to_seconds(*timecode_line.group(5, 6, 7, 8))
        body = " ".join(lines[text_start_index:]).strip()
        if not body or end <= start:
            continue
        segments.append(
            TranscriptSegment(start=round(start, 3), end=round(end, 3), text=body)
        )
    return segments


def _parse_json_segments(text: str) -> list[TranscriptSegment]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise STTServiceError(f"Invalid JSON transcript: {exc}") from exc

    raw_segments = payload.get("segments", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_segments, list):
        raise STTServiceError("JSON transcript must contain a list of segments.")

    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        start = item.get("start", item.get("start_sec"))
        end = item.get("end", item.get("end_sec"))
        body = str(item.get("text", "")).strip()
        if start is None or end is None or not body:
            continue
        start = float(start)
        end = float(end)
        if end <= start:
            continue
        segments.append(
            TranscriptSegment(start=round(start, 3), end=round(end, 3), text=body)
        )
    return segments
