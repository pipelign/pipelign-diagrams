from __future__ import annotations

import logging
import os


def configure_logging() -> int:
    """
    Configure the root logger level from the LOG_LEVEL environment variable.

    This ensures a single log level is applied consistently across all
    modules that use the standard logging package.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # If no handlers are configured on the root logger, attach a simple
    # stderr handler so that our logs are actually emitted (both under
    # unittest and when run via uvicorn).
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    return level
