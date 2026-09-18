"""Cross-process rate limiting with fixed-window counters in Redis.

Two windows are enforced together because providers publish both: a per-second
ceiling (which a burst breaks — e.g. liquidating five positions at once) and a
per-minute ceiling (which sustained polling breaks).

A fixed window is used rather than a leaky bucket because it needs only
``INCR`` + ``EXPIRE``: no Lua, no clock skew between workers, and the worst case
(2× the limit across a window boundary) is well inside the 20 % headroom left
by using 80 % of the published limits.

Redis failures fail *open* — a monitoring outage must not stop the trading loop.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from redis import Redis

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LimitDecision:
    """Outcome of a limiter check."""

    allowed: bool
    reason: str = ""
    retry_after: float = 0.0


def window_key(provider: str, endpoint_class: str, width: str, bucket: int) -> str:
    """Redis counter key for one provider/class/window instant."""
    return f"http:rate:{provider}:{endpoint_class}:{width}:{bucket}"


class RedisRateLimiter:
    """Fixed-window limiter for one provider/endpoint class."""

    def __init__(
        self,
        redis_client: Redis,
        provider: str,
        endpoint_class: str,
        per_second: int,
        per_minute: int,
    ) -> None:
        self._redis = redis_client
        self._provider = provider
        self._endpoint_class = endpoint_class
        self._per_second = per_second
        self._per_minute = per_minute

    @property
    def enabled(self) -> bool:
        """False when no budget is configured for this provider/class."""
        return self._per_second > 0 or self._per_minute > 0

    def acquire(self, now: Optional[float] = None) -> LimitDecision:
        """Consume one slot from both windows.

        Returns a refusal (with the seconds until the window rolls) instead of
        sleeping, so the caller — a Celery task on a 15-second beat — decides
        whether to wait, skip, or retry on the next tick.
        """
        if not self.enabled:
            return LimitDecision(allowed=True)

        now = now if now is not None else time.time()
        checks = (
            ("s", int(now), 1, self._per_second),
            ("m", int(now // 60), 60, self._per_minute),
        )

        for width, bucket, ttl, limit in checks:
            if limit <= 0:
                continue
            key = window_key(self._provider, self._endpoint_class, width, bucket)
            try:
                used = int(self._redis.incr(key))
                if used == 1:
                    self._redis.expire(key, ttl + 1)
            except Exception:
                logger.exception("Rate limiter %s unreadable — allowing the call", key)
                return LimitDecision(allowed=True)

            if used > limit:
                retry_after = 1.0 - (now - int(now)) if width == "s" else 60.0 - (now % 60)
                return LimitDecision(
                    allowed=False,
                    reason=(
                        f"{self._provider}/{self._endpoint_class} exceeded "
                        f"{limit} requests per {'second' if width == 's' else 'minute'}"
                    ),
                    retry_after=round(max(retry_after, 0.01), 3),
                )

        return LimitDecision(allowed=True)
