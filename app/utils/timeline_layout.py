from __future__ import annotations

from dataclasses import dataclass

from app.models.edit_plan import Clip, EditPlan, Marker
from app.utils.timecode import seconds_to_frames


@dataclass(frozen=True)
class TimelineClip:
    id: str
    name: str
    track: int
    source_start_sec: float
    source_end_sec: float
    timeline_start_sec: float
    timeline_end_sec: float
    reason: str


@dataclass(frozen=True)
class TimelineMarker:
    name: str
    comment: str
    time_sec: float
    frame: int


def build_timeline_clips(plan: EditPlan, fps: float) -> list[TimelineClip]:
    tracks: dict[int, list[Clip]] = {}
    for clip in plan.clips:
        tracks.setdefault(clip.track, []).append(clip)

    rendered: list[TimelineClip] = []
    for track_index in sorted(tracks):
        timeline_cursor = 0.0
        for clip_index, clip in enumerate(
            sorted(tracks[track_index], key=lambda item: item.start_sec),
            start=1,
        ):
            source_in_frames = seconds_to_frames(clip.start_sec, fps)
            source_out_frames = seconds_to_frames(clip.end_sec, fps)
            if source_out_frames <= source_in_frames:
                continue

            duration_frames = source_out_frames - source_in_frames
            timeline_start_frames = seconds_to_frames(timeline_cursor, fps)
            timeline_end_frames = timeline_start_frames + duration_frames
            timeline_cursor = timeline_end_frames / fps

            rendered.append(
                TimelineClip(
                    id=f"{track_index}-{clip_index}",
                    name=f"Clip {track_index}.{clip_index}",
                    track=track_index,
                    source_start_sec=round(clip.start_sec, 3),
                    source_end_sec=round(clip.end_sec, 3),
                    timeline_start_sec=round(timeline_start_frames / fps, 3),
                    timeline_end_sec=round(timeline_end_frames / fps, 3),
                    reason=clip.reason,
                )
            )
    return rendered


def build_timeline_markers(markers: list[Marker], fps: float) -> list[TimelineMarker]:
    rendered: list[TimelineMarker] = []
    for index, marker in enumerate(markers, start=1):
        rendered.append(
            TimelineMarker(
                name=f"Marker {index}",
                comment=marker.comment,
                time_sec=round(marker.time_sec, 3),
                frame=seconds_to_frames(marker.time_sec, fps),
            )
        )
    return rendered
