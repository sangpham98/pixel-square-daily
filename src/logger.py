"""Centralized logging configuration."""

from __future__ import annotations

import logging
import os
import sys


def setup_logger(name: str = "pixel") -> logging.Logger:
    """Configure and return the application logger.

    Respects LOG_LEVEL env var (default INFO).
    Outputs to stderr in a human-readable format.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


# Module-level logger shared across the app
log = setup_logger()
