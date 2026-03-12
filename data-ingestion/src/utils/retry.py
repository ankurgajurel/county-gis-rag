"""
Retry decorator with exponential backoff and jitter.

On transient failures (timeouts, 429s, 500s), we wait and try again:
  attempt 1: fail → wait ~1s
  attempt 2: fail → wait ~2s
  attempt 3: fail → wait ~4s
  attempt 4: give up, raise

Jitter adds randomness to the wait so multiple workers don't all retry
at the same instant and overwhelm the server.

Usage:
    @retry(max_attempts=3)
    async def fetch(url):
        ...
"""

import asyncio
import functools
import random
import logging

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
                        logger.error(
                            "All %d attempts failed for %s: %s",
                            max_attempts, func.__name__, e,
                        )
                        raise
                    # Exponential backoff with jitter
                    delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                    delay *= 0.5 + random.random()  # jitter: 50%-150% of delay
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                        attempt, max_attempts, func.__name__, e, delay,
                    )
                    await asyncio.sleep(delay)
            raise last_exception  # should never reach here
        return wrapper
    return decorator
