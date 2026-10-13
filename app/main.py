from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.plugin_routes import router as plugin_router
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.logging_setup import configure_logging, install_quiet_access_log_filter
from app.core.metrics import setup_metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(debug=settings.debug)
    if settings.suppress_poll_access_logs:
        install_quiet_access_log_filter()
    settings.ensure_storage()
    logger.info(
        "NeuroCut API started app={} debug={} storage={}",
        settings.app_name,
        settings.debug,
        settings.storage_path,
    )
    yield
    logger.info("NeuroCut API shutting down")


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

    setup_metrics(app)
    app.include_router(router)
    app.include_router(plugin_router)
    return app


app = create_app()
