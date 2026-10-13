from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MANIFEST_FILENAME = "sources_manifest.json"


@dataclass(frozen=True)
class SourceItem:
    index: int
    stored_path: str
    original_filename: str
    duration_sec: float
    global_offset_sec: float
    has_audio: bool

    @property
    def global_end_sec(self) -> float:
        return self.global_offset_sec + self.duration_sec


@dataclass(frozen=True)
class SourcesManifest:
    sources: list[SourceItem]
    total_duration_sec: float
    assembly_proxy: str = "proxy_480p.mp4"

    def resolve_global(self, global_sec: float) -> tuple[SourceItem, float]:
        """Map a global assembly timestamp to (source, local_sec)."""
        clamped = max(0.0, global_sec)
        for source in self.sources:
            if clamped < source.global_end_sec or source is self.sources[-1]:
                local = clamped - source.global_offset_sec
                local = max(0.0, min(local, source.duration_sec))
                return source, local
        last = self.sources[-1]
        return last, max(0.0, min(clamped - last.global_offset_sec, last.duration_sec))

    def prompt_block(self) -> str:
        lines = [
            "Sources are concatenated sequentially into one combined timeline:",
        ]
        for source in self.sources:
            lines.append(
                f"- #{source.index} \"{source.original_filename}\": "
                f"{source.global_offset_sec:.1f} .. {source.global_end_sec:.1f} s "
                f"(duration {source.duration_sec:.1f} s)"
            )
        lines.append(
            "Edit plan timestamps refer to the combined timeline. "
            "You may interleave clips from different sources for a mix."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "sources": [
                {
                    "index": s.index,
                    "stored_path": s.stored_path,
                    "original_filename": s.original_filename,
                    "duration_sec": s.duration_sec,
                    "global_offset_sec": s.global_offset_sec,
                    "has_audio": s.has_audio,
                }
                for s in self.sources
            ],
            "total_duration_sec": self.total_duration_sec,
            "assembly_proxy": self.assembly_proxy,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> SourcesManifest:
        sources = [
            SourceItem(
                index=int(item["index"]),
                stored_path=str(item["stored_path"]),
                original_filename=str(item["original_filename"]),
                duration_sec=float(item["duration_sec"]),
                global_offset_sec=float(item["global_offset_sec"]),
                has_audio=bool(item.get("has_audio", True)),
            )
            for item in payload.get("sources", [])
        ]
        return cls(
            sources=sources,
            total_duration_sec=float(payload.get("total_duration_sec", 0.0)),
            assembly_proxy=str(payload.get("assembly_proxy", "proxy_480p.mp4")),
        )


def load_sources_manifest(job_dir: Path) -> SourcesManifest | None:
    path = job_dir / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict) or not payload.get("sources"):
        return None
    return SourcesManifest.from_dict(payload)


def save_sources_manifest(job_dir: Path, manifest: SourcesManifest) -> Path:
    path = job_dir / MANIFEST_FILENAME
    path.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def resolve_clip_times(
    manifest: SourcesManifest,
    job_dir: Path,
    start_sec: float,
    end_sec: float,
) -> tuple[Path, float, float]:
    """Resolve global clip range to a single source file and local times.

    If the clip spans multiple sources, it is clamped to the source that
    contains the clip start (MVP behaviour).
    """
    source, local_start = manifest.resolve_global(start_sec)
    _, local_end_probe = manifest.resolve_global(max(end_sec - 0.05, start_sec))
    local_end = max(local_start + 0.05, local_end_probe)
    if local_end > source.duration_sec:
        local_end = source.duration_sec
    return (job_dir / source.stored_path).resolve(), local_start, local_end
