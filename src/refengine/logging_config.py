from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(log_file: Path | None = None, verbose: bool = False) -> None:
    """Configure local logging without exposing document contents."""
    shutdown_logging()
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )


def shutdown_logging() -> None:
    """Flush and close handlers so Windows can rename completed run folders."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        try:
            handler.flush()
            handler.close()
        finally:
            root.removeHandler(handler)
