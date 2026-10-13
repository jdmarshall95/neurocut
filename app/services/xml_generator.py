from __future__ import annotations

import json
import logging
import time
import uuid
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import ffmpeg
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import Settings, get_settings
from app.core.metrics import observe_stage
from app.models.edit_plan import Clip, EditPlan, Marker
from app.utils.media_path import build_relative_media_pathurl, resolve_media_filename
from app.utils.timecode import normalize_fps, seconds_to_frames

logger = logging.getLogger(__name__)


class XMLGenerationError(Exception):
    """Raised when FCP7 XML generation fails."""


@dataclass(frozen=True)
class VideoMetadata:
    fps: float
    duration_sec: float
    width: int
    height: int


@dataclass(frozen=True)
class RenderedClip:
    id: str
    name: str
    source_in: int
    source_out: int
    timeline_start: int
    timeline_end: int
    reason: str


@dataclass(frozen=True)
class RenderedTrack:
    index: int
    clips: list[RenderedClip]


@dataclass(frozen=True)
class RenderedMarker:
    name: str
    comment: str
    frame: int
    out_frame: int


@dataclass(frozen=True)
class XMLExportResult:
    job_id: str
    xml_path: Path
    sequence_duration_frames: int
    clip_count: int
    marker_count: int
    fps: float
    timebase: int
    media_filename: str


@dataclass(frozen=True)
class XMLDownloadPackage:
    job_id: str
    zip_path: Path
    xml_filename: str
    media_filename: str


class XMLGenerator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        templates_dir = Path(__file__).resolve().parent.parent / "templates"
        self._env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(default_for_string=False, default=False),
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
            raise XMLGenerationError(f"Original video not found in '{job_dir}'.")
        return candidates[0]

    def _load_edit_plan(self, job_id: str) -> EditPlan:
        edit_plan_path = self._job_dir(job_id) / "edit_plan.json"
        if not edit_plan_path.is_file():
            raise XMLGenerationError(
                f"Edit plan not found for job '{job_id}'. Run AI analysis first."
            )
        payload = json.loads(edit_plan_path.read_text(encoding="utf-8"))
        return EditPlan.model_validate(payload)

    def _parse_fps(self, raw_fps: str | None, default_fps: float) -> float:
        if not raw_fps:
            return default_fps
        try:
            if "/" in raw_fps:
                return float(Fraction(raw_fps))
            return float(raw_fps)
        except (ValueError, ZeroDivisionError):
            return default_fps

    def _probe_video(self, video_path: Path) -> VideoMetadata:
        try:
            probe = ffmpeg.probe(str(video_path), cmd=self.settings.ffprobe_path)
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            logger.warning("ffprobe failed for %s: %s", video_path, stderr.strip())
            return VideoMetadata(
                fps=self.settings.default_fps,
                duration_sec=0.0,
                width=1920,
                height=1080,
            )

        video_stream = next(
            (stream for stream in probe.get("streams", []) if stream.get("codec_type") == "video"),
            None,
        )
        format_info = probe.get("format", {})

        fps = self._parse_fps(
            video_stream.get("avg_frame_rate") if video_stream else None,
            self.settings.default_fps,
        )
        if fps <= 0:
            fps = self.settings.default_fps

        duration_sec = float(format_info.get("duration") or 0.0)
        width = int((video_stream or {}).get("width") or 1920)
        height = int((video_stream or {}).get("height") or 1080)

        return VideoMetadata(
            fps=fps,
            duration_sec=duration_sec,
            width=width,
            height=height,
        )

    def _build_tracks(self, plan: EditPlan, fps: float) -> list[RenderedTrack]:
        tracks: dict[int, list[Clip]] = {}
        for clip in plan.clips:
            tracks.setdefault(clip.track, []).append(clip)

        rendered_tracks: list[RenderedTrack] = []
        for track_index in sorted(tracks):
            timeline_cursor = 0
            rendered_clips: list[RenderedClip] = []
            for clip_index, clip in enumerate(
                sorted(tracks[track_index], key=lambda item: item.start_sec),
                start=1,
            ):
                source_in = seconds_to_frames(clip.start_sec, fps)
                source_out = seconds_to_frames(clip.end_sec, fps)
                if source_out <= source_in:
                    raise XMLGenerationError(
                        f"Invalid clip on track {track_index}: end must be after start."
                    )

                clip_duration = source_out - source_in
                timeline_start = timeline_cursor
                timeline_end = timeline_cursor + clip_duration
                timeline_cursor = timeline_end

                rendered_clips.append(
                    RenderedClip(
                        id=f"{track_index}-{clip_index}",
                        name=f"Clip {track_index}.{clip_index}",
                        source_in=source_in,
                        source_out=source_out,
                        timeline_start=timeline_start,
                        timeline_end=timeline_end,
                        reason=clip.reason,
                    )
                )

            rendered_tracks.append(RenderedTrack(index=track_index, clips=rendered_clips))

        return rendered_tracks

    def _build_markers(self, markers: list[Marker], fps: float) -> list[RenderedMarker]:
        rendered: list[RenderedMarker] = []
        for index, marker in enumerate(markers, start=1):
            frame = seconds_to_frames(marker.time_sec, fps)
            rendered.append(
                RenderedMarker(
                    name=f"Marker {index}",
                    comment=marker.comment,
                    frame=frame,
                    out_frame=frame + 1,
                )
            )
        return rendered

    def generate(self, job_id: str, *, save: bool = True) -> XMLExportResult:
        started = time.perf_counter()
        job_dir = self._job_dir(job_id)
        if not job_dir.is_dir():
            raise XMLGenerationError(f"Job directory not found: '{job_id}'.")

        plan = self._load_edit_plan(job_id)
        original_video = self._find_original_video(job_dir)
        metadata = self._probe_video(original_video)

        fps = metadata.fps or self.settings.default_fps
        timebase, ntsc = normalize_fps(fps)
        if self.settings.default_fps and metadata.duration_sec <= 0:
            fps = self.settings.default_fps
            timebase, ntsc = normalize_fps(fps)

        video_tracks = self._build_tracks(plan, fps)
        markers = self._build_markers(plan.markers, fps)

        source_duration_frames = seconds_to_frames(
            metadata.duration_sec,
            fps,
        )
        if source_duration_frames <= 0:
            max_source_out = max(
                (clip.source_out for track in video_tracks for clip in track.clips),
                default=0,
            )
            max_timeline_end = max(
                (clip.timeline_end for track in video_tracks for clip in track.clips),
                default=0,
            )
            source_duration_frames = max(max_source_out, max_timeline_end, 1)

        sequence_duration_frames = max(
            (
                clip.timeline_end
                for track in video_tracks
                for clip in track.clips
            ),
            default=0,
        )
        if markers:
            sequence_duration_frames = max(
                sequence_duration_frames,
                max(marker.frame for marker in markers) + 1,
            )
        sequence_duration_frames = max(sequence_duration_frames, 1)

        media_filename = resolve_media_filename(job_dir, original_video)
        media_pathurl = build_relative_media_pathurl(media_filename)

        template = self._env.get_template("fcp7_template.xml.j2")
        xml_content = template.render(
            sequence_uuid=str(uuid.uuid4()),
            sequence_name=f"NeuroCut {job_id[:8]}",
            sequence_duration_frames=sequence_duration_frames,
            timebase=timebase,
            ntsc="TRUE" if ntsc else "FALSE",
            width=metadata.width,
            height=metadata.height,
            source_filename=media_filename,
            pathurl=media_pathurl,
            source_duration_frames=source_duration_frames,
            video_tracks=video_tracks,
            markers=markers,
        )

        xml_path = job_dir / "neurocut_export.xml"
        if save:
            xml_path.write_text(xml_content, encoding="utf-8")

        clip_count = sum(len(track.clips) for track in video_tracks)
        elapsed = time.perf_counter() - started
        observe_stage("xml", elapsed)
        logger.info(
            "[export] job=%s xml=%s clips=%d markers=%d fps=%.3f timebase=%d elapsed=%.2fs",
            job_id,
            xml_path,
            clip_count,
            len(markers),
            fps,
            timebase,
            elapsed,
        )

        return XMLExportResult(
            job_id=job_id,
            xml_path=xml_path,
            sequence_duration_frames=sequence_duration_frames,
            clip_count=clip_count,
            marker_count=len(markers),
            fps=fps,
            timebase=timebase,
            media_filename=media_filename,
        )

    def create_download_package(self, job_id: str) -> XMLDownloadPackage:
        result = self.generate(job_id, save=True)
        job_dir = self._job_dir(job_id)
        original_video = self._find_original_video(job_dir)
        media_filename = result.media_filename
        xml_filename = f"neurocut_{job_id[:8]}.xml"
        zip_path = job_dir / "neurocut_export.zip"

        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(result.xml_path, arcname=xml_filename)
            archive.write(original_video, arcname=media_filename)

        logger.info(
            "[export] job=%s package=%s xml=%s media=%s",
            job_id,
            zip_path,
            xml_filename,
            media_filename,
        )

        return XMLDownloadPackage(
            job_id=job_id,
            zip_path=zip_path,
            xml_filename=xml_filename,
            media_filename=media_filename,
        )
