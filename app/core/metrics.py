"""Prometheus metrics for NeuroCut jobs and processing stages."""

from __future__ import annotations

from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

JOBS_TOTAL = Counter(
    "neurocut_jobs_total",
    "Total NeuroCut jobs by outcome and STT engine",
    labelnames=("status", "engine"),
)

PROCESSING_DURATION_SECONDS = Histogram(
    "neurocut_processing_duration_seconds",
    "Processing duration in seconds by pipeline stage",
    labelnames=("stage",),
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1200.0),
)

_VALID_ENGINES = frozenset({"whisper", "gigaam", "silero"})


def normalize_engine(engine: str | None) -> str:
    value = (engine or "whisper").strip().lower()
    return value if value in _VALID_ENGINES else "whisper"


def observe_stage(stage: str, duration_sec: float) -> None:
    PROCESSING_DURATION_SECONDS.labels(stage=stage).observe(max(duration_sec, 0.0))


def record_job(*, status: str, engine: str | None) -> None:
    outcome = "success" if status == "success" else "failed"
    JOBS_TOTAL.labels(status=outcome, engine=normalize_engine(engine)).inc()


def setup_metrics(app) -> Instrumentator:
    """Attach HTTP instrumentation and expose GET /metrics."""
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health"],
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)
    return instrumentator
