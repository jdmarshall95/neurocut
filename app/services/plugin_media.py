from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from app.core.config import Settings, get_settings
from app.utils.media_path import save_source_media

logger = logging.getLogger(__name__)

PLUGIN_SOURCE_FILENAME = "plugin_source.json"
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mxf"}


class PluginMediaError(Exception):
    """Raised when a local media path cannot be used by the Premiere plugin API."""


def validate_local_media_path(path: str | Path, settings: Settings | None = None) -> Path:
    """Resolve and authorize a local filesystem path for plugin ingest."""
    settings = settings or get_settings()
    if not settings.plugin_enabled:
        raise PluginMediaError("Plugin API is disabled (PLUGIN_ENABLED=false).")

    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise PluginMediaError(f"Media file not found: {resolved}")

    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_VIDEO_SUFFIXES:
        raise PluginMediaError(
            f"Unsupported media type '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_VIDEO_SUFFIXES))}"
        )

    if settings.plugin_allow_any_local_path:
        return resolved

    allowed_roots = settings.resolved_plugin_allowed_roots
    if not allowed_roots:
        raise PluginMediaError(
            "Local path rejected. Configure PLUGIN_ALLOWED_ROOTS or set "
            "PLUGIN_ALLOW_ANY_LOCAL_PATH=true for development."
        )

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    raise PluginMediaError(
        f"Path '{resolved}' is outside PLUGIN_ALLOWED_ROOTS."
    )


def save_plugin_source(job_dir: Path, local_path: Path) -> Path:
    """Persist the user's original media path for Premiere timeline apply."""
    job_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "local_path": str(local_path),
        "original_filename": local_path.name,
    }
    output_path = job_dir / PLUGIN_SOURCE_FILENAME
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_source_media(
        job_dir,
        original_filename=local_path.name,
        stored_filename=local_path.name,
    )
    return output_path


def load_plugin_source(job_dir: Path) -> dict[str, str] | None:
    meta_path = job_dir / PLUGIN_SOURCE_FILENAME
    if not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def resolve_plugin_media_path(job_dir: Path, stored_video: Path | None = None) -> Path:
    """Return the path Premiere should use (user's local file when available)."""
    meta = load_plugin_source(job_dir)
    if meta:
        local_path = Path(str(meta.get("local_path", ""))).expanduser()
        if local_path.is_file():
            return local_path.resolve()

    if stored_video is not None and stored_video.is_file():
        return stored_video.resolve()

    candidates = sorted(
        path for path in job_dir.glob("original.*") if path.is_file()
    )
    if candidates:
        return candidates[0].resolve()

    raise PluginMediaError(f"No media file found for job '{job_dir.name}'.")


def prepare_job_media(
    local_path: Path,
    job_id: str,
    settings: Settings | None = None,
) -> Path:
    """Register plugin source metadata; optionally mirror into job storage."""
    settings = settings or get_settings()
    job_dir = (settings.storage_path / job_id).resolve()
    save_plugin_source(job_dir, local_path)

    if settings.plugin_copy_media_to_storage:
        suffix = local_path.suffix or ".mp4"
        stored = job_dir / f"original{suffix}"
        if not stored.exists() or stored.stat().st_size != local_path.stat().st_size:
            shutil.copy2(local_path, stored)
        logger.info("[plugin] copied media to %s", stored)
        return stored

    logger.info("[plugin] using reference path %s", local_path)
    return local_path
