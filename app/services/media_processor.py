from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import ffmpeg

from app.core.config import Settings, get_settings
from app.utils.sources_manifest import (
    SourceItem,
    SourcesManifest,
    save_sources_manifest,
)


class MediaProcessingError(Exception):
    """Raised when FFmpeg media processing fails."""


@dataclass(frozen=True)
class MediaProcessingResult:
    job_id: str
    original_path: Path
    audio_path: Path | None
    proxy_video_path: Path
    has_audio: bool
    duration_sec: float | None = None
    scene_proxy_video_path: Path | None = None


class MediaProcessor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.storage = self.settings.ensure_storage()
        self._ensure_ffmpeg_available()

    def _ensure_ffmpeg_available(self) -> None:
        if shutil.which(self.settings.ffmpeg_path) is None:
            raise MediaProcessingError(
                f"FFmpeg not found at '{self.settings.ffmpeg_path}'. "
                "Install FFmpeg and ensure it is on PATH."
            )

    def _job_dir(self, job_id: str) -> Path:
        job_dir = (self.storage / job_id).resolve()
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def _assert_inside_storage(self, path: Path) -> Path:
        resolved = path.resolve()
        storage = self.storage.resolve()
        try:
            resolved.relative_to(storage)
        except ValueError as exc:
            raise MediaProcessingError(
                f"Output path must be inside storage directory: {path}"
            ) from exc
        return resolved

    def _default_audio_path(self, job_id: str) -> Path:
        return self._assert_inside_storage(self._job_dir(job_id) / "audio.wav")

    def _default_proxy_path(self, job_id: str) -> Path:
        return self._assert_inside_storage(self._job_dir(job_id) / "proxy_480p.mp4")

    def _default_scene_proxy_path(self, job_id: str) -> Path:
        return self._assert_inside_storage(
            self._job_dir(job_id) / self.settings.scene_proxy_filename
        )

    def _probe_media(self, video_path: Path) -> tuple[bool, float]:
        try:
            probe = ffmpeg.probe(str(video_path), cmd=self.settings.ffprobe_path)
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise MediaProcessingError(
                f"Failed to probe media '{video_path}': {stderr.strip()}"
            ) from exc

        has_audio = any(
            stream.get("codec_type") == "audio"
            for stream in probe.get("streams", [])
        )
        duration = float(probe.get("format", {}).get("duration") or 0.0)
        return has_audio, duration

    def extract_audio(
        self,
        video_path: Path,
        output_path: Path | None = None,
        *,
        job_id: str | None = None,
        has_audio: bool | None = None,
        duration_sec: float | None = None,
    ) -> Path | None:
        source = Path(video_path).resolve()
        if not source.is_file():
            raise MediaProcessingError(f"Video file not found: {source}")

        if has_audio is None or duration_sec is None:
            probed_has_audio, probed_duration = self._probe_media(source)
            has_audio = probed_has_audio if has_audio is None else has_audio
            duration_sec = probed_duration if duration_sec is None else duration_sec

        if not has_audio:
            return None

        if output_path is None:
            if job_id is None:
                job_id = uuid.uuid4().hex
            destination = self._default_audio_path(job_id)
        else:
            destination = self._assert_inside_storage(Path(output_path))

        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            (
                ffmpeg.input(str(source))
                .output(
                    str(destination),
                    acodec="pcm_s16le",
                    ac=self.settings.audio_channels,
                    ar=self.settings.audio_sample_rate,
                    vn=None,
                )
                .overwrite_output()
                .run(
                    cmd=self.settings.ffmpeg_path,
                    capture_stdout=True,
                    capture_stderr=True,
                )
            )
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise MediaProcessingError(
                f"Failed to extract audio from '{source}': {stderr.strip()}"
            ) from exc

        if not destination.is_file() or destination.stat().st_size == 0:
            raise MediaProcessingError(
                f"Audio extraction produced an empty or missing file: {destination}"
            )

        return destination

    def create_proxy_video(
        self,
        video_path: Path,
        output_path: Path | None = None,
        *,
        job_id: str | None = None,
        has_audio: bool | None = None,
    ) -> Path:
        source = Path(video_path).resolve()
        if not source.is_file():
            raise MediaProcessingError(f"Video file not found: {source}")

        if has_audio is None:
            has_audio, _ = self._probe_media(source)

        if output_path is None:
            if job_id is None:
                job_id = uuid.uuid4().hex
            destination = self._default_proxy_path(job_id)
        else:
            destination = self._assert_inside_storage(Path(output_path))

        destination.parent.mkdir(parents=True, exist_ok=True)
        height = self.settings.proxy_height

        output_kwargs: dict[str, object] = {
            "vf": f"scale=-2:{height}",
            "vcodec": "libx264",
            "preset": "fast",
            "crf": 28,
        }
        if has_audio:
            output_kwargs["acodec"] = "aac"
            output_kwargs["audio_bitrate"] = "128k"
        else:
            output_kwargs["an"] = None

        try:
            (
                ffmpeg.input(str(source))
                .output(str(destination), **output_kwargs)
                .overwrite_output()
                .run(
                    cmd=self.settings.ffmpeg_path,
                    capture_stdout=True,
                    capture_stderr=True,
                )
            )
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise MediaProcessingError(
                f"Failed to create proxy video from '{source}': {stderr.strip()}"
            ) from exc

        if not destination.is_file() or destination.stat().st_size == 0:
            raise MediaProcessingError(
                f"Proxy video generation produced an empty or missing file: {destination}"
            )

        return destination

    def create_scene_proxy_video(
        self,
        video_path: Path,
        output_path: Path | None = None,
        *,
        job_id: str | None = None,
    ) -> Path:
        """Heavily compressed low-fps proxy for fast scene detection."""
        source = Path(video_path).resolve()
        if not source.is_file():
            raise MediaProcessingError(f"Video file not found: {source}")

        if output_path is None:
            if job_id is None:
                job_id = uuid.uuid4().hex
            destination = self._default_scene_proxy_path(job_id)
        else:
            destination = self._assert_inside_storage(Path(output_path))

        destination.parent.mkdir(parents=True, exist_ok=True)
        height = self.settings.scene_proxy_height
        fps = self.settings.scene_proxy_fps
        vf = f"scale=-2:{height},fps={fps}"

        try:
            (
                ffmpeg.input(str(source))
                .output(
                    str(destination),
                    vf=vf,
                    vcodec="libx264",
                    preset=self.settings.scene_proxy_preset,
                    crf=self.settings.scene_proxy_crf,
                    an=None,
                    movflags="+faststart",
                )
                .overwrite_output()
                .run(
                    cmd=self.settings.ffmpeg_path,
                    capture_stdout=True,
                    capture_stderr=True,
                )
            )
        except ffmpeg.Error as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
            raise MediaProcessingError(
                f"Failed to create scene proxy from '{source}': {stderr.strip()}"
            ) from exc

        if not destination.is_file() or destination.stat().st_size == 0:
            raise MediaProcessingError(
                f"Scene proxy generation produced an empty or missing file: {destination}"
            )

        return destination

    def process_video(
        self,
        video_path: Path,
        job_id: str | None = None,
        *,
        reference_source: bool = False,
    ) -> MediaProcessingResult:
        source = Path(video_path).resolve()
        if not source.is_file():
            raise MediaProcessingError(f"Video file not found: {source}")

        resolved_job_id = job_id or uuid.uuid4().hex
        job_dir = self._job_dir(resolved_job_id)

        if reference_source:
            working_source = source
            recorded_original = source
        else:
            stored_original = self._assert_inside_storage(job_dir / source.name)
            if source != stored_original:
                shutil.copy2(source, stored_original)
            working_source = stored_original
            recorded_original = stored_original

        has_audio, duration_sec = self._probe_media(working_source)
        audio_path = self.extract_audio(
            working_source,
            job_id=resolved_job_id,
            has_audio=has_audio,
            duration_sec=duration_sec,
        )
        proxy_video_path = self.create_proxy_video(
            working_source,
            job_id=resolved_job_id,
            has_audio=has_audio,
        )
        scene_proxy_video_path = self.create_scene_proxy_video(
            working_source,
            job_id=resolved_job_id,
        )

        return MediaProcessingResult(
            job_id=resolved_job_id,
            original_path=recorded_original,
            audio_path=audio_path,
            proxy_video_path=proxy_video_path,
            scene_proxy_video_path=scene_proxy_video_path,
            has_audio=has_audio,
            duration_sec=duration_sec or None,
        )

    def _concat_media_files(
        self,
        inputs: list[Path],
        output_path: Path,
        *,
        audio_only: bool = False,
    ) -> Path:
        if not inputs:
            raise MediaProcessingError("No input files provided for concatenation.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        list_file = output_path.parent / f"concat_{output_path.stem}.txt"
        list_file.write_text(
            "\n".join(f"file '{path.resolve()}'" for path in inputs) + "\n",
            encoding="utf-8",
        )
        output_kwargs: dict[str, object] = {"movflags": "+faststart"}
        if audio_only:
            output_kwargs.update(
                {
                    "acodec": "pcm_s16le",
                    "ac": self.settings.audio_channels,
                    "ar": self.settings.audio_sample_rate,
                    "vn": None,
                }
            )
        else:
            output_kwargs.update(
                {
                    "vcodec": "libx264",
                    "preset": "fast",
                    "crf": 28,
                    "acodec": "aac",
                    "audio_bitrate": "128k",
                }
            )
        try:
            (
                ffmpeg.input(str(list_file), format="concat", safe=0)
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
            raise MediaProcessingError(
                f"Failed to concatenate media files: {stderr.strip()}"
            ) from exc
        finally:
            list_file.unlink(missing_ok=True)

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise MediaProcessingError(
                f"Concatenation produced an empty file: {output_path}"
            )
        return output_path

    def process_multiple_videos(
        self,
        upload_paths: list[Path],
        job_id: str,
    ) -> MediaProcessingResult:
        """Process N source videos into one assembly timeline for AI mixing."""
        if len(upload_paths) < 2:
            raise MediaProcessingError("process_multiple_videos requires at least 2 files.")

        job_dir = self._job_dir(job_id)
        sources_dir = job_dir / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        source_items: list[SourceItem] = []
        proxy_parts: list[Path] = []
        audio_parts: list[Path] = []
        global_offset = 0.0
        any_audio = False

        for index, upload_path in enumerate(upload_paths, start=1):
            source = Path(upload_path).resolve()
            if not source.is_file():
                raise MediaProcessingError(f"Video file not found: {source}")

            suffix = source.suffix or ".mp4"
            stored = sources_dir / f"source_{index:03d}{suffix}"
            if source != stored:
                shutil.copy2(source, stored)

            has_audio, duration_sec = self._probe_media(stored)
            any_audio = any_audio or has_audio

            per_proxy = sources_dir / f"proxy_{index:03d}.mp4"
            self.create_proxy_video(
                stored,
                output_path=per_proxy,
                has_audio=has_audio,
            )
            proxy_parts.append(per_proxy)

            if has_audio:
                per_audio = sources_dir / f"audio_{index:03d}.wav"
                extracted = self.extract_audio(
                    stored,
                    output_path=per_audio,
                    has_audio=True,
                    duration_sec=duration_sec,
                )
                if extracted is not None:
                    audio_parts.append(extracted)

            source_items.append(
                SourceItem(
                    index=index,
                    stored_path=str(stored.relative_to(job_dir)),
                    original_filename=source.name,
                    duration_sec=duration_sec,
                    global_offset_sec=global_offset,
                    has_audio=has_audio,
                )
            )
            global_offset += duration_sec

        assembly_proxy = self._default_proxy_path(job_id)
        self._concat_media_files(proxy_parts, assembly_proxy, audio_only=False)
        scene_proxy_video_path = self.create_scene_proxy_video(
            assembly_proxy,
            job_id=job_id,
        )

        audio_path: Path | None = None
        if audio_parts:
            audio_path = self._default_audio_path(job_id)
            self._concat_media_files(audio_parts, audio_path, audio_only=True)

        manifest = SourcesManifest(
            sources=source_items,
            total_duration_sec=global_offset,
            assembly_proxy=assembly_proxy.name,
        )
        save_sources_manifest(job_dir, manifest)

        # Keep compatibility: first source also available as original.* symlink target.
        first_source = (job_dir / source_items[0].stored_path).resolve()
        legacy_original = job_dir / f"original{first_source.suffix}"
        if not legacy_original.exists():
            shutil.copy2(first_source, legacy_original)

        from app.utils.media_path import save_source_media

        save_source_media(
            job_dir,
            original_filename=", ".join(item.original_filename for item in source_items),
            stored_filename=manifest.assembly_proxy,
        )

        return MediaProcessingResult(
            job_id=job_id,
            original_path=first_source,
            audio_path=audio_path,
            proxy_video_path=assembly_proxy,
            scene_proxy_video_path=scene_proxy_video_path,
            has_audio=any_audio,
            duration_sec=global_offset or None,
        )
