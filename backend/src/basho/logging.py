"""Logging estruturado em JSON via structlog."""

import logging
import sys

import structlog

DEFAULT_LOG_LEVEL = logging.INFO


def configure_logging(level: int = DEFAULT_LOG_LEVEL) -> None:
    """Configura structlog para emitir JSON em stdout."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.typing.FilteringBoundLogger:
    """Retorna um logger estruturado nomeado."""
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger
