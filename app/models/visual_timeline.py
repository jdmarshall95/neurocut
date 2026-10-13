from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TimelineSource = Literal["speech", "visual"]


class VisualShot(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    index: int = Field(ge=1)
    label: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> VisualShot:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class VisualTimeline(BaseModel):
    source: TimelineSource = "visual"
    duration: float | None = None
    scene_threshold: float = Field(gt=0)
    shot_count: int = Field(ge=0)
    shots: list[VisualShot] = Field(min_length=1)
