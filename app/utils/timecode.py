from __future__ import annotations


def seconds_to_frames(seconds: float, fps: float) -> int:
    return max(0, round(seconds * fps))


def frames_to_timecode(frames: int, fps: float) -> str:
    if fps <= 0:
        raise ValueError("FPS must be positive.")

    total_seconds, frame_number = divmod(frames, int(round(fps)))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frame_number:02d}"


def normalize_fps(fps: float) -> tuple[int, bool]:
    if abs(fps - 29.97) < 0.1 or abs(fps - 59.94) < 0.1:
        return 30, True
    if abs(fps - 23.976) < 0.1:
        return 24, True
    return max(1, round(fps)), False
