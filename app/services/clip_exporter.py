from __future__ import annotations

import json
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import ffmpeg

from app.core.config import Settings, get_settings
from app.models.edit_plan import Clip, EditPlan
from app.services.media_processor import MediaProcessor
from app.utils.sources_manifest import load_sources_manifest, resolve_clip_times

logger = logging.getLogger(__name__)


class ClipExportError(Exception):
    """Raised when FFmpeg clip export fails."""


@dataclass(frozen=True)
class ClipExportResult:
    job_id: str
    clips_dir: Path
    zip_path: Path
    clip_count: int
    marker_count: int
    manifest_path: Path


class ClipExporter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ensure_ffmpeg_available()

    def _ensure_ffmpeg_available(self) -> None:
        if shutil.which(self.settings.ffmpeg_path) is None:
            raise ClipExportError(
                f"FFmpeg not found at '{self.settings.ffmpeg_path}'. "
                "Install FFmpeg and ensure it is on PATH."
            )

    def _job_dir(self, job_id: str) -> Path:
        return (self.settings.storage_path / job_id).resolve()

    def _clips_dir(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "clips_export"

    def _load_edit_plan(self, job_id: str) -> EditPlan:
        edit_plan_path = self._job_dir(job_id) / "edit_plan.json"
        if not edit_plan_path.is_file():
            raise ClipExportError(
                f"Edit plan not found for job '{job_id}'. Run AI analysis first."
            )
        return EditPlan.model_validate_json(edit_plan_path.read_text(encoding="utf-8"))

    def _find_original_video(self, job_dir: Path) -> Path:
        candidates = sorted(
            path for path in job_dir.iterdir() if path.is_file() and path.name.startswith("original.")
        )
        if not candidates:
            raise ClipExportError(f"Original video not found in '{job_dir}'.")
        return candidates[0]

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        minutes, secs = divmod(max(0.0, seconds), 60.0)
        hours, minutes = divmod(minutes, 60.0)
        return f"{int(hours):02d}h{int(minutes):02d}m{secs:06.3f}s"

    def _clip_filename(self, index: int, clip: Clip) -> str:
        start_label = self._format_timestamp(clip.start_sec).replace(".", "_")
        end_label = self._format_timestamp(clip.end_sec).replace(".", "_")
        return f"clip_{index:03d}_t{clip.track}_{start_label}-{end_label}.mp4"

    def _export_clip(
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
            "preset": "fast",
            "crf": 23,
            "movflags": "+faststart",
            "pix_fmt": "yuv420p",
        }
        if has_audio:
            output_kwargs["acodec"] = "aac"
            output_kwargs["audio_bitrate"] = "128k"
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
            raise ClipExportError(
                f"Failed to export clip [{local_start:.3f}-{local_end:.3f}]: "
                f"{stderr.strip()}"
            ) from exc

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise ClipExportError(f"Clip export produced an empty file: {output_path}")

    def _ordered_clips(self, plan: EditPlan) -> list[Clip]:
        return sorted(plan.clips, key=lambda clip: (clip.track, clip.start_sec))

    def _write_manifest(
        self,
        *,
        job_id: str,
        plan: EditPlan,
        source_video: Path,
        entries: list[dict[str, object]],
        manifest_path: Path,
    ) -> None:
        payload = {
            "job_id": job_id,
            "source_video": str(source_video.resolve()),
            "clip_count": len(entries),
            "marker_count": len(plan.markers),
            "markers": [marker.model_dump() for marker in plan.markers],
            "clips": entries,
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_zip(self, clips_dir: Path, zip_path: Path) -> None:
        if zip_path.is_file():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(clips_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(clips_dir).as_posix())

    def generate(self, job_id: str, *, save: bool = True) -> ClipExportResult:
        job_dir = self._job_dir(job_id)
        if not job_dir.is_dir():
            raise ClipExportError(f"Job directory not found: '{job_id}'.")

        plan = self._load_edit_plan(job_id)
        manifest = load_sources_manifest(job_dir)
        default_source = self._find_original_video(job_dir)
        clips_dir = self._clips_dir(job_id)
        zip_path = self._job_dir(job_id) / "neurocut_clips.zip"

        if save:
            if clips_dir.exists():
                shutil.rmtree(clips_dir)
            clips_dir.mkdir(parents=True, exist_ok=True)

            manifest_entries: list[dict[str, object]] = []
            for index, clip in enumerate(self._ordered_clips(plan), start=1):
                filename = self._clip_filename(index, clip)
                output_path = clips_dir / filename
                if manifest is not None:
                    source_video, local_start, local_end = resolve_clip_times(
                        manifest,
                        job_dir,
                        clip.start_sec,
                        clip.end_sec,
                    )
                else:
                    source_video = default_source
                    local_start = clip.start_sec
                    local_end = clip.end_sec
                has_audio, _ = MediaProcessor(self.settings)._probe_media(source_video)
                self._export_clip(
                    source_video=source_video,
                    local_start=local_start,
                    local_end=local_end,
                    output_path=output_path,
                    has_audio=has_audio,
                )
                manifest_entries.append(
                    {
                        "index": index,
                        "filename": filename,
                        "track": clip.track,
                        "start_sec": clip.start_sec,
                        "end_sec": clip.end_sec,
                        "duration_sec": round(clip.end_sec - clip.start_sec, 3),
                        "reason": clip.reason,
                    }
                )

            manifest_path = clips_dir / "manifest.json"
            self._write_manifest(
                job_id=job_id,
                plan=plan,
                source_video=default_source,
                entries=manifest_entries,
                manifest_path=manifest_path,
            )
            self._write_zip(clips_dir, zip_path)
        else:
            manifest_path = clips_dir / "manifest.json"

        logger.info(
            "[clips] job=%s exported clips=%d zip=%s",
            job_id,
            len(plan.clips),
            zip_path,
        )

        return ClipExportResult(
            job_id=job_id,
            clips_dir=clips_dir,
            zip_path=zip_path,
            clip_count=len(plan.clips),
            marker_count=len(plan.markers),
            manifest_path=manifest_path,
        )
