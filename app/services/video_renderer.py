from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import ffmpeg

from app.core.config import Settings, get_settings
from app.models.edit_plan import Clip, EditPlan
from app.services.media_processor import MediaProcessor
from app.utils.sources_manifest import load_sources_manifest, resolve_clip_times

logger = logging.getLogger(__name__)

RENDER_FILENAME = "neurocut_render.mp4"


class VideoRenderError(Exception):
    """Raised when the stitched clip render fails."""


@dataclass(frozen=True)
class VideoRenderResult:
    job_id: str
    render_path: Path
    clip_count: int
    duration_sec: float


class VideoRenderer:
    """Phase 15 — turnkey clip: cut clips per edit plan and stitch into one MP4."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ensure_ffmpeg_available()

    def _ensure_ffmpeg_available(self) -> None:
        if shutil.which(self.settings.ffmpeg_path) is None:
            raise VideoRenderError(
                f"FFmpeg not found at '{self.settings.ffmpeg_path}'. "
                "Install FFmpeg and ensure it is on PATH."
            )

    def _job_dir(self, job_id: str) -> Path:
        return (self.settings.storage_path / job_id).resolve()

    def _load_edit_plan(self, job_id: str) -> EditPlan:
        edit_plan_path = self._job_dir(job_id) / "edit_plan.json"
        if not edit_plan_path.is_file():
            raise VideoRenderError(
                f"Edit plan not found for job '{job_id}'. Run AI analysis first."
            )
        return EditPlan.model_validate_json(edit_plan_path.read_text(encoding="utf-8"))

    def _find_original_video(self, job_dir: Path) -> Path:
        candidates = sorted(
            path
            for path in job_dir.iterdir()
            if path.is_file() and path.name.startswith("original.")
        )
        if not candidates:
            raise VideoRenderError(f"Original video not found in '{job_dir}'.")
        return candidates[0]

    @staticmethod
    def _ordered_clips(plan: EditPlan) -> list[Clip]:
        return sorted(plan.clips, key=lambda clip: (clip.track, clip.start_sec))

    def _clip_source(
        self,
        job_dir: Path,
        clip: Clip,
    ) -> tuple[Path, float, float, bool]:
        manifest = load_sources_manifest(job_dir)
        if manifest is not None:
            source_video, local_start, local_end = resolve_clip_times(
                manifest,
                job_dir,
                clip.start_sec,
                clip.end_sec,
            )
            has_audio, _ = MediaProcessor(self.settings)._probe_media(source_video)
            return source_video, local_start, local_end, has_audio

        source_video = self._find_original_video(job_dir)
        has_audio, _ = MediaProcessor(self.settings)._probe_media(source_video)
        return source_video, clip.start_sec, clip.end_sec, has_audio

    def _cut_part(
        self,
        *,
        source_video: Path,
        local_start: float,
        local_end: float,
        output_path: Path,
        has_audio: bool,
    ) -> None:
        duration = max(local_end - local_start, 0.05)
        output_kwargs: dict[str, object] = {
            "vcodec": "libx264",
            "preset": self.settings.render_preset,
            "crf": self.settings.render_crf,
            "pix_fmt": "yuv420p",
            # Force a constant frame rate / SAR so concat demuxer stays happy.
            "video_track_timescale": 90000,
        }
        if has_audio:
            output_kwargs["acodec"] = "aac"
            output_kwargs["audio_bitrate"] = self.settings.render_audio_bitrate
            output_kwargs["ar"] = 48000
        else:
            output_kwargs["an"] = None

        try:
            (
                ffmpeg.input(str(source_video), ss=local_start, t=duration)
                .output(str(output_path), **output_kwargs)
                .overwrite_output()
                .run(
                    cmd=self.settings.ffmpeg_path,
                    capture_stdout=True,
                    capture_stderr=True,
                )
            )
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise VideoRenderError(
                f"Failed to cut clip [{local_start:.3f}-{local_end:.3f}]: "
                f"{stderr.strip()}"
            ) from exc

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise VideoRenderError(f"Clip cut produced an empty file: {output_path}")

    def _concat_parts(self, parts: list[Path], output_path: Path, parts_dir: Path) -> None:
        list_file = parts_dir / "concat.txt"
        list_file.write_text(
            "\n".join(f"file '{part.name}'" for part in parts) + "\n",
            encoding="utf-8",
        )

        try:
            (
                ffmpeg.input(str(list_file), format="concat", safe=0)
                .output(str(output_path), c="copy", movflags="+faststart")
                .overwrite_output()
                .run(
                    cmd=self.settings.ffmpeg_path,
                    capture_stdout=True,
                    capture_stderr=True,
                )
            )
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise VideoRenderError(f"Failed to concatenate clips: {stderr.strip()}") from exc

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise VideoRenderError("Stitched render produced an empty file.")

    def render(self, job_id: str, *, save: bool = True) -> VideoRenderResult:
        job_dir = self._job_dir(job_id)
        if not job_dir.is_dir():
            raise VideoRenderError(f"Job directory not found: '{job_id}'.")

        plan = self._load_edit_plan(job_id)
        ordered = self._ordered_clips(plan)
        render_path = job_dir / RENDER_FILENAME
        parts_dir = job_dir / "render_parts"

        if save:
            if parts_dir.exists():
                shutil.rmtree(parts_dir)
            parts_dir.mkdir(parents=True, exist_ok=True)

            parts: list[Path] = []
            for index, clip in enumerate(ordered, start=1):
                part_path = parts_dir / f"part_{index:03d}.mp4"
                source_video, local_start, local_end, has_audio = self._clip_source(
                    job_dir,
                    clip,
                )
                self._cut_part(
                    source_video=source_video,
                    local_start=local_start,
                    local_end=local_end,
                    output_path=part_path,
                    has_audio=has_audio,
                )
                parts.append(part_path)

            self._concat_parts(parts, render_path, parts_dir)
            shutil.rmtree(parts_dir, ignore_errors=True)

        total_duration = round(
            sum(max(clip.end_sec - clip.start_sec, 0.0) for clip in ordered), 3
        )

        logger.info(
            "[render] job=%s stitched clips=%d duration=%.2fs -> %s",
            job_id,
            len(ordered),
            total_duration,
            render_path,
        )

        return VideoRenderResult(
            job_id=job_id,
            render_path=render_path,
            clip_count=len(ordered),
            duration_sec=total_duration,
        )
