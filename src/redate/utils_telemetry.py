"""
redate/utils_telemetry.py
Configures structured JSON logging suitable for R2 storage and CloudWatch.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog

from .utils_date import get_beijing_today

__all__ = ["logger", "configure_logging"]


def setup_logging_paths() -> Path:
    """Ensure logs directory exists."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Generate filename based on execution time
    filename = f"redate-{get_beijing_today().strftime('%Y-%m-%d')}.log"
    return log_dir / filename


def configure_logging() -> None:
    log_file = setup_logging_paths()

    # Define processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ]

    # Console (GitHub Actions) + File (Artifact/R2)
    # Using standard logging to handle file output easily
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    # Structlog configuration
    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger()
# Initialize on import
configure_logging()
