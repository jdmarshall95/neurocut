"""Component health probes for GET /health."""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings

HealthStatus = Literal["ok", "degraded", "unhealthy"]

# Absolute free-space thresholds (percentage alone is noisy on large disks).
_DISK_DEGRADED_FREE_BYTES = 5 * 1024**3  # 5 GiB
_DISK_UNHEALTHY_FREE_BYTES = 1 * 1024**3  # 1 GiB
_LLM_CACHE_TTL_SEC = 60.0

_llm_cache_lock = threading.Lock()
_llm_cache: dict[str, Any] = {"expires_at": 0.0, "result": None}


@dataclass(frozen=True)
class ComponentResult:
    status: HealthStatus
    detail: str
    extra: dict[str, Any]


def _worst(*statuses: HealthStatus) -> HealthStatus:
    order = {"ok": 0, "degraded": 1, "unhealthy": 2}
    return max(statuses, key=lambda item: order[item])


def check_storage(settings: Settings) -> ComponentResult:
    path = settings.ensure_storage()
    usage = shutil.disk_usage(path)
    free_ratio = usage.free / usage.total if usage.total else 0.0
    used_percent = round((1.0 - free_ratio) * 100.0, 2)

    if usage.free < _DISK_UNHEALTHY_FREE_BYTES:
        status: HealthStatus = "unhealthy"
        detail = f"Disk critically low ({usage.free} bytes free, {used_percent}% used)"
    elif usage.free < _DISK_DEGRADED_FREE_BYTES:
        status = "degraded"
        detail = f"Low disk space ({usage.free} bytes free, {used_percent}% used)"
    else:
        status = "ok"
        detail = f"Storage OK ({usage.free} bytes free, {used_percent}% used)"

    return ComponentResult(
        status=status,
        detail=detail,
        extra={
            "path": str(path),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "used_percent": used_percent,
        },
    )


def _probe_gemini(settings: Settings) -> ComponentResult:
    if not settings.gemini_api_key.strip():
        return ComponentResult(
            status="degraded",
            detail="GEMINI_API_KEY is not configured",
            extra={"provider": "gemini"},
        )
    try:
        from app.core.llm import create_gemini_client

        client = create_gemini_client(settings)
        # Lightweight reachability check — list at most one model page.
        models = client.models.list(config={"page_size": 1})
        next(iter(models), None)
        return ComponentResult(
            status="ok",
            detail="Gemini API reachable",
            extra={"provider": "gemini"},
        )
    except Exception as exc:  # noqa: BLE001 — health probe must never raise
        return ComponentResult(
            status="degraded",
            detail=f"Gemini probe failed: {exc}",
            extra={"provider": "gemini"},
        )


def _probe_deepseek(settings: Settings) -> ComponentResult:
    if not settings.deepseek_api_key.strip():
        return ComponentResult(
            status="degraded",
            detail="DEEPSEEK_API_KEY is not configured",
            extra={"provider": "deepseek"},
        )
    return ComponentResult(
        status="ok",
        detail="DeepSeek API key configured",
        extra={"provider": "deepseek"},
    )


def check_llm(settings: Settings) -> ComponentResult:
    provider = settings.resolved_llm_provider
    cache_key = f"{provider}:{bool(settings.gemini_api_key)}:{bool(settings.deepseek_api_key)}"
    now = time.monotonic()

    with _llm_cache_lock:
        cached = _llm_cache.get("result")
        if (
            cached is not None
            and _llm_cache.get("cache_key") == cache_key
            and float(_llm_cache.get("expires_at", 0.0)) > now
        ):
            return cached

    if provider == "deepseek":
        result = _probe_deepseek(settings)
    else:
        result = _probe_gemini(settings)

    with _llm_cache_lock:
        _llm_cache["cache_key"] = cache_key
        _llm_cache["expires_at"] = now + _LLM_CACHE_TTL_SEC
        _llm_cache["result"] = result
    return result


def build_health_payload(settings: Settings) -> tuple[HealthStatus, dict[str, Any]]:
    storage = check_storage(settings)
    llm = check_llm(settings)
    overall = _worst(storage.status, llm.status)

    payload = {
        "status": overall,
        "app_name": settings.app_name,
        "checks": {
            "storage": {
                "status": storage.status,
                "detail": storage.detail,
                **storage.extra,
            },
            "llm": {
                "status": llm.status,
                "detail": llm.detail,
                **llm.extra,
            },
        },
    }
    return overall, payload
