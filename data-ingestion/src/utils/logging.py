"""
Logging setup.

Configures Python's standard logging with a clean format that includes
timestamps and module names. Used everywhere via:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("Discovered %d layers", count)

Call setup_logging() once at startup (in cli.py).
"""

import logging
import sys

from src.config import settings


def setup_logging():
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )

    # Quiet down noisy libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
