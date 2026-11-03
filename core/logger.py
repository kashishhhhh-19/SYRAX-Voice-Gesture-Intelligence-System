"""
core/logger.py - Centralized Thread-Safe Logging for SYRAX
Outputs structured log entries to both terminal and logs/syrax.log.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import config


def setup_logger(
    name: str = "SYRAX",
    log_file: Optional[Path] = None,
    level: int = logging.INFO
) -> logging.Logger:
    """
    Configure and retrieve a logger with dual stream and file handlers.
    Thread-safe and idempotent.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-7s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (Stream)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    target_file = log_file or config.LOG_FILE
    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as exc:
        print(f"[LOGGER WARNING] Could not initialize file handler at {target_file}: {exc}")

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    Return a namespaced child logger under the SYRAX hierarchy.
    """
    return setup_logger(f"SYRAX.{module_name}")
