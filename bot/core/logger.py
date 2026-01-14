from __future__ import annotations

import logging
from typing import Any, Dict

import structlog


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


def get_logger(**context: Dict[str, Any]) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger().bind(**context)
