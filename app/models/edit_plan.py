from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Clip(BaseModel):
    start_sec: float = Field(
        ge=0,
        description=(
            "Clip start in absolute seconds from video start. "
            "Use one decimal place: 1.0 means 1 second, 12.5 means 12.5 seconds. "
            "Never write 0.01 for 1 second or 0.12 for 12 seconds."
        ),
    )
    end_sec: float = Field(
        ge=0,
        description=(
            "Clip end in absolute seconds from video start. "
            "Use one decimal place, same unit as start_sec."
        ),
    )
    track: int = Field(ge=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> Clip:
        if self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        return self


class Marker(BaseModel):
    time_sec: float = Field(
        ge=0,
        description=(
            "Marker time in absolute seconds from video start. "
            "Use one decimal place (e.g. 8.0, 15.5)."
        ),
    )
    comment: str = Field(min_length=1)


class EditPlan(BaseModel):
    clips: list[Clip] = Field(min_length=1)
    markers: list[Marker] = Field(default_factory=list)
