from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

SOURCE_MEDIA_FILENAME = "source_media.json"


def save_source_media(
    job_dir: Path,
    *,
    original_filename: str,
    stored_filename: str,
) -> None:
    payload = {
        "original_filename": Path(original_filename).name,
        "stored_filename": stored_filename,
    }
    (job_dir / SOURCE_MEDIA_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_source_media(job_dir: Path) -> dict[str, str] | None:
    meta_path = job_dir / SOURCE_MEDIA_FILENAME
    if not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def resolve_media_filename(job_dir: Path, stored_video: Path) -> str:
    meta = load_source_media(job_dir)
    if meta:
        original = str(meta.get("original_filename", "")).strip()
        if original:
            return Path(original).name
    return stored_video.name


def build_relative_media_pathurl(media_filename: str) -> str:
    """FCP7 pathurl: media sits next to the XML (same folder after unzipping)."""
    name = Path(media_filename).name
    return f"file://./{quote(name)}"
