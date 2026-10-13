import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.plugin_routes import router as plugin_router
from app.api.routes import router
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _configure_logging(settings: Settings) -> None:
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    logging.getLogger("app").setLevel(level)
    if settings.suppress_poll_access_logs:
        _install_quiet_access_log_filter()


class _QuietAccessLogFilter(logging.Filter):
    """Hide noisy status/health polling from uvicorn access logs."""

    _QUIET_MARKERS = (
        ' "GET /health ',
        ' "GET /jobs/',
    )
    _QUIET_SUFFIXES = (
        "/status ",
        "/transcription/status ",
        "/analysis/status ",
        "/subtitles/status ",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if not any(marker in message for marker in self._QUIET_MARKERS):
            return True
        if ' "GET /health ' in message:
            return False
        return not any(suffix in message for suffix in self._QUIET_SUFFIXES)


def _install_quiet_access_log_filter() -> None:
    quiet_filter = _QuietAccessLogFilter()
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(logger_name).addFilter(quiet_filter)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings)
    settings.ensure_storage()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    if app_settings.plugin_cors_allow_all:
        cors_origins = ["*"]
        cors_credentials = False
    else:
        cors_origins = list(app_settings.api_cors_origins)
        cors_credentials = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(plugin_router)
    return app


app = create_app()
