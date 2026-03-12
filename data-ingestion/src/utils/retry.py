"""Retry decorator with exponential backoff + jitter."""

import asyncio
import functools
import logging
import random

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 30.0,
    retryable_exceptions: tuple = (Exception,),
):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error("All %d attempts failed for %s: %s", max_attempts, func.__name__, e)
                        raise
                    delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                    delay *= 0.5 + random.random()
                    logger.warning("Attempt %d/%d failed for %s: %s. Retry in %.1fs", attempt, max_attempts, func.__name__, e, delay)
                    await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
