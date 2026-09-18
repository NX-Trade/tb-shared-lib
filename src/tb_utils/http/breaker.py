"""Circuit breaker whose state is shared across processes via Redis.

``RequestMaker`` kept ``failure_count`` and ``state`` on the instance, and a new
instance was built per request (``UpstoxAdapter._request`` created one every
call). The breaker therefore never actually tripped: the counter was discarded
before it could reach the threshold, and even a long-lived instance only
protected its own worker while three other workers kept hammering the provider.

State here lives in Redis under one key per provider/endpoint class, so every
worker sees the same breaker:

* **CLOSED** — calls flow, consecutive failures counted.
* **OPEN** — calls rejected immediately for ``reset_timeout``.
* **HALF_OPEN** — exactly one trial call is admitted; success closes the
  breaker, failure re-opens it for another timeout.

Redis being unavailable must not stop trading, so every operation fails open
(treated as CLOSED) and is logged.
"""

import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

from redis import Redis

logger = logging.getLogger(__name__)


class BreakerState(IntEnum):
    """Values also written to ``external_api_request.circuit_breaker_state``."""

    OPEN = 0
    CLOSED = 1
    HALF_OPEN = 2


@dataclass(frozen=True)
class BreakerConfig:
    """Thresholds for one breaker."""

    max_failures: int = 5
    reset_timeout_seconds: float = 60.0


def breaker_key(provider: str, endpoint_class: str) -> str:
    """Redis hash holding the shared breaker state."""
    return f"http:breaker:{provider}:{endpoint_class}"


class RedisCircuitBreaker:
    """Shared-state circuit breaker for one provider/endpoint class."""

    def __init__(
        self,
        redis_client: Redis,
        provider: str,
        endpoint_class: str = "other",
        config: Optional[BreakerConfig] = None,
    ) -> None:
        self._redis = redis_client
        self._provider = provider
        self._endpoint_class = endpoint_class
        self._config = config or BreakerConfig()
        self._key = breaker_key(provider, endpoint_class)

    # ── Queries ────────────────────────────────────────────────────────────

    def state(self) -> BreakerState:
        """Current state, promoting OPEN → HALF_OPEN once the timeout elapses."""
        try:
            raw = self._redis.hgetall(self._key)
        except Exception:
            logger.exception("Breaker %s unreadable — treating as CLOSED", self._key)
            return BreakerState.CLOSED

        if not raw:
            return BreakerState.CLOSED

        data = {_text(k): _text(v) for k, v in raw.items()}
        state = BreakerState(int(data.get("state", BreakerState.CLOSED)))
        if state is not BreakerState.OPEN:
            return state

        opened_at = float(data.get("opened_at", 0.0))
        if time.time() - opened_at >= self._config.reset_timeout_seconds:
            self._set_state(BreakerState.HALF_OPEN)
            logger.info("Breaker %s → HALF_OPEN (trial call allowed)", self._key)
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    def allows_request(self) -> bool:
        """False only when the breaker is fully OPEN."""
        return self.state() is not BreakerState.OPEN

    # ── Transitions ────────────────────────────────────────────────────────

    def record_success(self) -> None:
        """Clear failures and close the breaker."""
        try:
            previous = BreakerState(int(_text(self._redis.hget(self._key, "state")) or 1))
            self._redis.hset(self._key, mapping={"state": int(BreakerState.CLOSED), "failures": 0})
            if previous is not BreakerState.CLOSED:
                logger.info("Breaker %s → CLOSED after a successful call", self._key)
        except Exception:
            logger.exception("Could not record breaker success for %s", self._key)

    def record_failure(self) -> BreakerState:
        """Count a failure and open the breaker if the threshold is reached.

        Returns the state after the update so the caller can alert on the
        CLOSED → OPEN edge exactly once.
        """
        try:
            failures = int(self._redis.hincrby(self._key, "failures", 1))
            # Expire idle breakers so a provider that recovered days ago does
            # not carry stale counters forever.
            self._redis.expire(self._key, int(self._config.reset_timeout_seconds * 10))
        except Exception:
            logger.exception("Could not record breaker failure for %s", self._key)
            return BreakerState.CLOSED

        if failures < self._config.max_failures:
            return BreakerState.CLOSED

        self._set_state(BreakerState.OPEN)
        logger.warning(
            "Breaker %s → OPEN after %d consecutive failures (blocking for %.0fs)",
            self._key,
            failures,
            self._config.reset_timeout_seconds,
        )
        return BreakerState.OPEN

    def reset(self) -> None:
        """Force the breaker closed (operator action, tests)."""
        try:
            self._redis.delete(self._key)
        except Exception:
            logger.exception("Could not reset breaker %s", self._key)

    # ── Internals ──────────────────────────────────────────────────────────

    def _set_state(self, state: BreakerState) -> None:
        mapping: dict[str, object] = {"state": int(state)}
        if state is BreakerState.OPEN:
            mapping["opened_at"] = time.time()
        try:
            self._redis.hset(self._key, mapping=mapping)
        except Exception:
            logger.exception("Could not set breaker %s to %s", self._key, state.name)


def _text(value: object) -> str:
    """Decode a Redis value that may arrive as bytes or str."""
    if value is None:
        return ""
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)
