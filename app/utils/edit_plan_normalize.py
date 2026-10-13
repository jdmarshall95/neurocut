from __future__ import annotations

import logging

from app.models.edit_plan import Clip, EditPlan

logger = logging.getLogger(__name__)

MIN_PLAUSIBLE_TIMELINE_RATIO = 0.2
MIN_ABSOLUTE_TIMELINE_SEC = 5.0


def is_sparse_speech(
    segments: list[object],
    duration: float | None,
    *,
    min_coverage_ratio: float = 0.12,
    max_segments_for_short_speech: int = 2,
    max_spoken_sec_for_short_speech: float = 3.0,
) -> bool:
    if not segments:
        return True

    spoken_sec = 0.0
    for segment in segments:
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        if start is None or end is None and isinstance(segment, dict):
            start = segment.get("start", 0.0)
            end = segment.get("end", 0.0)
        spoken_sec += max(float(end) - float(start), 0.0)

    if duration and duration > 0 and spoken_sec / duration < min_coverage_ratio:
        return True

    return (
        len(segments) <= max_segments_for_short_speech
        and spoken_sec < max_spoken_sec_for_short_speech
    )


def _timeline_max(plan: EditPlan) -> float:
    clip_max = max((clip.end_sec for clip in plan.clips), default=0.0)
    marker_max = max((marker.time_sec for marker in plan.markers), default=0.0)
    return max(clip_max, marker_max)


def _detect_timestamp_scale(timeline_max: float, duration: float) -> float | None:
    if timeline_max <= 0:
        return None

    if timeline_max >= duration * MIN_PLAUSIBLE_TIMELINE_RATIO:
        return None
    if timeline_max >= MIN_ABSOLUTE_TIMELINE_SEC and timeline_max <= duration * 1.05:
        return None

    ratio = duration / timeline_max

    if timeline_max <= 1.0:
        # 0.01..0.21 on a 20s video is usually hundredths, not 0-1 normalization.
        if ratio >= 50.0:
            return ratio
        return duration

    if 10.0 <= ratio <= 1000.0:
        return ratio

    return None


def _round_to_tenths(value: float, *, duration: float | None = None) -> float:
    rounded = round(value, 1)
    if duration is not None:
        rounded = min(rounded, round(duration, 1))
    return max(0.0, rounded)


def _apply_clip_timestamps(clip: Clip, *, duration: float | None) -> Clip:
    start_sec = _round_to_tenths(clip.start_sec, duration=duration)
    end_sec = _round_to_tenths(clip.end_sec, duration=duration)
    if end_sec <= start_sec:
        end_sec = _round_to_tenths(min(start_sec + 0.5, duration or start_sec + 0.5), duration=duration)
    return clip.model_copy(update={"start_sec": start_sec, "end_sec": end_sec})


def normalize_edit_plan_timestamps(
    plan: EditPlan,
    duration: float | None,
) -> EditPlan:
    if duration is None or duration <= 0:
        return EditPlan(
            clips=[_apply_clip_timestamps(clip, duration=duration) for clip in plan.clips],
            markers=[
                marker.model_copy(
                    update={"time_sec": _round_to_tenths(marker.time_sec, duration=duration)}
                )
                for marker in plan.markers
            ],
        )

    timeline_max = _timeline_max(plan)
    scale = _detect_timestamp_scale(timeline_max, duration) if duration > 3 else None

    if scale is not None:
        logger.warning(
            "[edit_plan] rescaling timestamps x%.2f (timeline_max=%.3fs video_duration=%.1fs)",
            scale,
            timeline_max,
            duration,
        )

    clips: list[Clip] = []
    for clip in plan.clips:
        start_sec = clip.start_sec * scale if scale else clip.start_sec
        end_sec = clip.end_sec * scale if scale else clip.end_sec
        clips.append(
            _apply_clip_timestamps(
                clip.model_copy(update={"start_sec": start_sec, "end_sec": end_sec}),
                duration=duration,
            )
        )

    markers = [
        marker.model_copy(
            update={
                "time_sec": _round_to_tenths(
                    marker.time_sec * scale if scale else marker.time_sec,
                    duration=duration,
                )
            }
        )
        for marker in plan.markers
    ]

    return EditPlan(clips=clips, markers=markers)
