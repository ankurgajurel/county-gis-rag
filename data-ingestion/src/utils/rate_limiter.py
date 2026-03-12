"""
Token bucket rate limiter for async HTTP requests.

Why token bucket: it smooths out bursty traffic. Instead of sending 10 requests
instantly then waiting 2 seconds, it spreads them evenly — 5/sec by default.

Usage:
    limiter = RateLimiter(rate=5.0, burst=10)
    async with limiter:
        await session.get(url)  # blocks if we're over the limit
"""

import asyncio
import time


class RateLimiter:
    def __init__(self, rate: float = 5.0, burst: int = 10):
        """
        Args:
            rate: Requests per second (steady state)
            burst: Max tokens stored — allows short bursts above rate
        """
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens < 1.0:
                wait = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(wait)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *exc):
        pass
