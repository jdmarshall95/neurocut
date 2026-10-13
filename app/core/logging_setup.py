"""Loguru-based application logging.

DEBUG → colored human-readable stderr.
Production (DEBUG=false) → structured JSON lines.
"""

from __future__ import annotations

import logging
import sys

from loguru import logger


class InterceptHandler(logging.Handler):
    """Forward stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(*, debug: bool) -> None:
    logger.remove()

    if debug:
        logger.add(
            sys.stderr,
            level="DEBUG",
            colorize=True,
            backtrace=True,
            diagnose=True,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
        )
    else:
        logger.add(
            sys.stderr,
            level="INFO",
            serialize=True,
            backtrace=False,
            diagnose=False,
        )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "app"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False


class QuietAccessLogFilter(logging.Filter):
    """Hide noisy polling / scrape traffic from uvicorn access logs."""

    _QUIET_PATH_MARKERS = (
        ' "GET /health ',
        ' "GET /metrics ',
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
        if ' "GET /health ' in message or ' "GET /metrics ' in message:
            return False
        if not any(marker in message for marker in self._QUIET_PATH_MARKERS):
            return True
        return not any(suffix in message for suffix in self._QUIET_SUFFIXES)


def install_quiet_access_log_filter() -> None:
    quiet_filter = QuietAccessLogFilter()
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(logger_name).addFilter(quiet_filter)
