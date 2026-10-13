from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically so concurrent readers never see a partial file.

    Writes to a temp file in the same directory, then os.replace() which is
    atomic on POSIX and Windows. Prevents JSONDecodeError races when a status
    endpoint reads while the pipeline is mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def read_json_resilient(
    path: Path,
    *,
    retries: int = 3,
    retry_delay_sec: float = 0.05,
) -> dict[str, Any] | None:
    """Read+parse JSON, tolerating transient empty/partial reads.

    Returns None if the file does not exist. Retries a few times on decode
    errors (e.g. a rare read that races a non-atomic writer), then gives up
    and returns None instead of raising.
    """
    if not path.is_file():
        return None

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            raw = path.read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("empty progress file")
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(retry_delay_sec)

    if last_error is not None:
        return None
    return None
