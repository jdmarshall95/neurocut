from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import ffmpeg

from app.core.config import Settings, get_settings
from app.models.visual_timeline import VisualShot, VisualTimeline

logger = logging.getLogger(__name__)

PTS_TIME_PATTERN = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


class SceneDetectionError(Exception):
    """Raised when FFmpeg scene detection fails."""


@dataclass(frozen=True)
class SceneDetectionResult:
    job_id: str
    timeline_path: Path
    shot_count: int
    duration: float | None


class SceneDetector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _job_dir(self, job_id: str) -> Path:
        return (self.settings.storage_path / job_id).resolve()

    def resolve_detection_video(self, video_path: Path, *, job_id: str | None = None) -> Path:
        """Prefer lightweight scene proxy when available."""
        source = Path(video_path).resolve()
        if job_id is not None:
            scene_proxy = self._job_dir(job_id) / self.settings.scene_proxy_filename
            if scene_proxy.is_file():
                return scene_proxy
        if source.name == "proxy_480p.mp4" and job_id is None:
            scene_proxy = source.parent / self.settings.scene_proxy_filename
            if scene_proxy.is_file():
                return scene_proxy
        return source

    def _parse_fps(self, raw_fps: str | None, default_fps: float) -> float:
        if not raw_fps:
            return default_fps
        try:
            if "/" in raw_fps:
                return float(Fraction(raw_fps))
            return float(raw_fps)
        except (ValueError, ZeroDivisionError):
            return default_fps

    def _probe_duration(self, video_path: Path) -> float:
        try:
            probe = ffmpeg.probe(str(video_path), cmd=self.settings.ffprobe_path)
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise SceneDetectionError(
                f"Failed to probe video '{video_path}': {stderr.strip()}"
            ) from exc

        format_info = probe.get("format", {})
        duration = float(format_info.get("duration") or 0.0)
        if duration <= 0:
            video_stream = next(
                (
                    stream
                    for stream in probe.get("streams", [])
                    if stream.get("codec_type") == "video"
                ),
                None,
            )
            if video_stream:
                fps = self._parse_fps(
                    video_stream.get("avg_frame_rate"),
                    self.settings.default_fps,
                )
                frame_count = float(video_stream.get("nb_frames") or 0.0)
                if frame_count > 0 and fps > 0:
                    duration = frame_count / fps

        if duration <= 0:
            raise SceneDetectionError(f"Could not determine duration for '{video_path}'.")
        return duration

    def _detect_cut_times(self, video_path: Path, *, threshold: float) -> list[float]:
        filter_expr = f"select='gt(scene,{threshold})',showinfo"
        command = [
            self.settings.ffmpeg_path,
            "-hide_banner",
            "-i",
            str(video_path),
            "-filter:v",
            filter_expr,
            "-an",
            "-f",
            "null",
            "-",
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise SceneDetectionError(
                f"Failed to run FFmpeg scene detection: {exc}"
            ) from exc

        if completed.returncode not in {0, 255}:
            stderr = completed.stderr.strip()
            raise SceneDetectionError(
                f"FFmpeg scene detection failed for '{video_path}': {stderr}"
            )

        cut_times: list[float] = []
        for line in completed.stderr.splitlines():
            match = PTS_TIME_PATTERN.search(line)
            if match:
                cut_times.append(float(match.group(1)))

        return sorted(set(cut_times))

    def _merge_close_cuts(
        self,
        cut_times: list[float],
        *,
        min_scene_duration: float,
    ) -> list[float]:
        if not cut_times:
            return []

        merged: list[float] = []
        previous = 0.0
        for cut in cut_times:
            if cut - previous >= min_scene_duration:
                merged.append(cut)
                previous = cut
        return merged

    def _build_shots(
        self,
        cut_times: list[float],
        duration: float,
        *,
        min_scene_duration: float,
    ) -> list[VisualShot]:
        boundaries = [0.0, *cut_times, duration]
        shots: list[VisualShot] = []

        for index in range(len(boundaries) - 1):
            start = round(boundaries[index], 3)
            end = round(boundaries[index + 1], 3)
            if end - start < min_scene_duration:
                continue
            shots.append(
                VisualShot(
                    start=start,
                    end=end,
                    index=len(shots) + 1,
                    label=f"Shot {len(shots) + 1}",
                )
            )

        if not shots:
            shots.append(
                VisualShot(
                    start=0.0,
                    end=round(duration, 3),
                    index=1,
                    label="Shot 1",
                )
            )
        elif shots[-1].end < duration - 0.05:
            tail_start = shots[-1].end
            if duration - tail_start >= min_scene_duration:
                shots.append(
                    VisualShot(
                        start=round(tail_start, 3),
                        end=round(duration, 3),
                        index=len(shots) + 1,
                        label=f"Shot {len(shots) + 1}",
                    )
                )

        return shots

    def detect(
        self,
        video_path: Path,
        *,
        job_id: str,
        save: bool = True,
        threshold: float | None = None,
        min_scene_duration: float | None = None,
    ) -> SceneDetectionResult:
        source = Path(video_path).resolve()
        if not source.is_file():
            raise SceneDetectionError(f"Video file not found: {source}")

        scene_threshold = threshold if threshold is not None else self.settings.scene_threshold
        min_duration = (
            min_scene_duration
            if min_scene_duration is not None
            else self.settings.min_scene_duration_sec
        )

        detection_source = self.resolve_detection_video(source, job_id=job_id)
        duration = self._probe_duration(detection_source)
        raw_cuts = self._detect_cut_times(detection_source, threshold=scene_threshold)
        cut_times = self._merge_close_cuts(raw_cuts, min_scene_duration=min_duration)
        shots = self._build_shots(cut_times, duration, min_scene_duration=min_duration)

        timeline = VisualTimeline(
            source="visual",
            duration=round(duration, 3),
            scene_threshold=scene_threshold,
            shot_count=len(shots),
            shots=shots,
        )

        timeline_path = self._job_dir(job_id) / "visual_timeline.json"
        if save:
            timeline_path.write_text(
                timeline.model_dump_json(indent=2),
                encoding="utf-8",
            )

        logger.info(
            "[scenes] job=%s shots=%d duration=%.1fs threshold=%.2f source=%s",
            job_id,
            len(shots),
            duration,
            scene_threshold,
            detection_source.name,
        )

        return SceneDetectionResult(
            job_id=job_id,
            timeline_path=timeline_path,
            shot_count=len(shots),
            duration=timeline.duration,
        )
