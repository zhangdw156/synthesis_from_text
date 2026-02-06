"""Unified logging configuration for GEM and experiments.

Use from experiments::

    from gem import setup_logging
    setup_logging(level="INFO", log_file=None)
    # or from Hydra config:
    setup_logging(**cfg.logging)
"""

import logging
from pathlib import Path
from typing import Any


DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    format: str | None = None,
    **kwargs: Any,
) -> None:
    """Configure root logging for the process.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: If set, also write logs to this file (UTF-8). Directory is created if needed.
        format: Log message format string; None uses DEFAULT_FORMAT.
        **kwargs: Ignored; allows passing full Hydra cfg.logging without error.
    """
    fmt = format if format else DEFAULT_FORMAT
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, (level or "INFO").upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
        force=True,
    )
