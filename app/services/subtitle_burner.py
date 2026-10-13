from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

SUBTITLED_FILENAME = "neurocut_subtitled.mp4"
SRT_FILENAME = "subtitles.srt"

# Cyrillic-capable fonts bundled in the Docker image (see assets/fonts +
# Dockerfile). "name" must match the font family reported by fontconfig so
# libass (burn-in) and fc-match (UI preview endpoint) resolve the exact file.
SUBTITLE_FONTS: list[dict[str, str]] = [
    {"name": "Manrope", "label": "Manrope"},
    {"name": "Unbounded", "label": "Unbounded"},
    {"name": "Bebas Neue", "label": "Bebas Neue"},
    {"name": "Coolvetica", "label": "Coolvetica"},
    {"name": "Days One", "label": "Days One"},
    {"name": "Playfair Display", "label": "Playfair Display"},
    {"name": "AngelicaC", "label": "Angelica"},
]


def available_fonts() -> list[dict[str, str]]:
    return [dict(font) for font in SUBTITLE_FONTS]


class SubtitleBurnError(Exception):
    """Raised when subtitle burn-in fails."""


@dataclass
class SubtitleSegment:
    start: float
    end: float
    text: str


@dataclass
class SubtitleStyle:
    font_size: int
    primary_color: str
    outline_color: str
    outline: int
    margin_v: int
    font_name: str = "Manrope"
    border_style: int = 1


@dataclass(frozen=True)
class SubtitleBurnResult:
    job_id: str
    output_path: Path
    srt_path: Path
    segment_count: int


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(segments: list[SubtitleSegment]) -> str:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.text.strip()
        if not text:
            continue
        end = max(segment.end, segment.start + 0.2)
        lines.append(str(index))
        lines.append(f"{_srt_timestamp(segment.start)} --> {_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


class SubtitleBurner:
    """Phase 16/17 — burn approved transcript text onto the original video."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ensure_ffmpeg_available()

    def _ensure_ffmpeg_available(self) -> None:
        if shutil.which(self.settings.ffmpeg_path) is None:
            raise SubtitleBurnError(
                f"FFmpeg not found at '{self.settings.ffmpeg_path}'. "
                "Install FFmpeg and ensure it is on PATH."
            )

    def _job_dir(self, job_id: str) -> Path:
        return (self.settings.storage_path / job_id).resolve()

    def _find_original_video(self, job_dir: Path) -> Path:
        candidates = sorted(
            path
            for path in job_dir.iterdir()
            if path.is_file() and path.name.startswith("original.")
        )
        if not candidates:
            raise SubtitleBurnError(f"Original video not found in '{job_dir}'.")
        return candidates[0]

    def _probe_frame_width(self, video: Path) -> int:
        """Best-effort video width in pixels; falls back to 1920."""
        try:
            import ffmpeg

            probe = ffmpeg.probe(str(video), cmd=self.settings.ffprobe_path)
            for stream in probe.get("streams", []):
                if stream.get("codec_type") == "video":
                    width = int(stream.get("width") or 0)
                    if width > 0:
                        return width
        except Exception as exc:  # noqa: BLE001 - probing is best-effort
            logger.warning("[subtitles] frame width probe failed: %s", exc)
        return 1920

    def default_style(self) -> SubtitleStyle:
        return SubtitleStyle(
            font_size=self.settings.subtitle_font_size,
            primary_color=self.settings.subtitle_primary_color,
            outline_color=self.settings.subtitle_outline_color,
            outline=self.settings.subtitle_outline,
            margin_v=self.settings.subtitle_margin_v,
            font_name=self.settings.subtitle_font_name,
            border_style=self.settings.subtitle_border_style,
        )

    def _force_style(self, style: SubtitleStyle) -> str:
        # ASS style overrides applied by libass. Alignment=2 => bottom center.
        font_name = (style.font_name or "Manrope").replace(",", " ")
        border_style = style.border_style if style.border_style in (1, 3) else 1
        return (
            f"FontName={font_name},"
            f"FontSize={style.font_size},"
            f"PrimaryColour={style.primary_color},"
            f"OutlineColour={style.outline_color},"
            f"BorderStyle={border_style},Outline={style.outline},Shadow=0,"
            f"Alignment=2,MarginV={style.margin_v}"
        )

    def burn(
        self,
        job_id: str,
        segments: list[SubtitleSegment],
        *,
        style: SubtitleStyle | None = None,
        auto_chunk: bool | None = None,
        max_words: int | None = None,
    ) -> SubtitleBurnResult:
        job_dir = self._job_dir(job_id)
        if not job_dir.is_dir():
            raise SubtitleBurnError(f"Job directory not found: '{job_id}'.")

        clean_segments = [s for s in segments if s.text.strip()]
        if not clean_segments:
            raise SubtitleBurnError("No non-empty subtitle segments provided.")

        source_video = self._find_original_video(job_dir)
        style = style or self.default_style()

        if auto_chunk is None:
            auto_chunk = self.settings.subtitle_auto_chunk
        if auto_chunk:
            from app.utils.subtitle_chunker import chunk_subtitle_segments

            frame_width = self._probe_frame_width(source_video)
            clean_segments = chunk_subtitle_segments(
                clean_segments,
                frame_width=frame_width,
                font_size=style.font_size,
                char_ratio=self.settings.subtitle_char_ratio,
                side_margin=self.settings.subtitle_side_margin,
                max_words=max_words or self.settings.subtitle_max_words,
            )
            if not clean_segments:
                raise SubtitleBurnError("No non-empty subtitle segments provided.")
            logger.info(
                "[subtitles] job=%s chunked to %d segments (frame_width=%d, max_words=%d)",
                job_id,
                len(clean_segments),
                frame_width,
                max_words or self.settings.subtitle_max_words,
            )

        srt_path = job_dir / SRT_FILENAME
        srt_path.write_text(build_srt(clean_segments), encoding="utf-8")

        output_path = job_dir / SUBTITLED_FILENAME
        vf = f"subtitles={SRT_FILENAME}:force_style='{self._force_style(style)}'"

        command = [
            self.settings.ffmpeg_path,
            "-hide_banner",
            "-y",
            "-i",
            source_video.name,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            self.settings.subtitle_preset,
            "-crf",
            str(self.settings.subtitle_crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:a",
            "copy",
            SUBTITLED_FILENAME,
        ]

        # Run inside the job dir so the subtitles filter gets a bare relative
        # filename (avoids the notoriously fragile path escaping of libass).
        try:
            completed = subprocess.run(
                command,
                cwd=str(job_dir),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise SubtitleBurnError(f"Failed to run FFmpeg subtitle burn: {exc}") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            # Retry once copying audio failed (e.g. incompatible codec) with AAC.
            if "could not" in stderr.lower() or "Invalid" in stderr:
                command[command.index("copy")] = "aac"
                completed = subprocess.run(
                    command,
                    cwd=str(job_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            if completed.returncode != 0:
                raise SubtitleBurnError(
                    f"FFmpeg subtitle burn failed: {(completed.stderr or '').strip()[-800:]}"
                )

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise SubtitleBurnError("Subtitle burn produced an empty file.")

        logger.info(
            "[subtitles] job=%s burned segments=%d -> %s",
            job_id,
            len(clean_segments),
            output_path,
        )

        return SubtitleBurnResult(
            job_id=job_id,
            output_path=output_path,
            srt_path=srt_path,
            segment_count=len(clean_segments),
        )
