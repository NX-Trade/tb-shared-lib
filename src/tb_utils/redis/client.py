"""One place that builds Redis clients.

There were 39 construction sites across the services, each calling
``Redis.from_url(...)`` directly. Two problems with that:

* **A pool per call site.** ``from_url`` creates a new ``ConnectionPool`` every
  time, so a worker that touched Redis from six modules held six pools. Code that
  built a client *inside* a function (the Upstox adapter, the trading-halt check)
  created a fresh pool on every invocation.
* **Inconsistent decoding.** Most sites passed ``decode_responses=True``; a few
  did not, so their callers had to remember to ``.decode()``. The same key read
  through two modules returned ``str`` in one and ``bytes`` in the other.

``get_redis()`` caches one client per distinct configuration, so pools are shared,
and makes ``decode_responses=True`` the default because that is what the majority
of existing callers assume. Byte-mode is still available explicitly for callers
that want it.

Connection URL resolution order (unchanged from the ad-hoc sites):
``REDIS_URL`` → ``CELERY_BROKER_URL`` → ``redis://localhost:6379/0``.
"""

import logging
import os
import threading
from typing import Optional

from redis import Redis

logger = logging.getLogger(__name__)

DEFAULT_URL = "redis://localhost:6379/0"

# Short by design: every caller is on a latency-sensitive path (a 15-second beat,
# an order decision). A hung Redis must fail fast rather than stall a tick.
DEFAULT_TIMEOUT_SECONDS = 2.0

_clients: dict[tuple, Redis] = {}
_lock = threading.Lock()


def resolve_redis_url(url: Optional[str] = None) -> str:
    """Return the Redis URL to use, honouring the historical env fallback chain."""
    return url or os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or DEFAULT_URL


def get_redis(
    url: Optional[str] = None,
    *,
    decode_responses: bool = True,
    socket_timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Redis:
    """Return a shared Redis client for the given configuration.

    Clients are cached per ``(url, decode_responses, socket_timeout)``, so
    repeated calls reuse one connection pool instead of creating another.

    Args:
        url: Override the resolved URL (mostly for tests).
        decode_responses: ``True`` (default) returns ``str``; pass ``False`` only
            when the caller genuinely wants ``bytes``.
        socket_timeout: Applied to both connect and read.

    Returns:
        A ``Redis`` client. Construction does not connect, so this does not raise
        on an unreachable server — the first command does.
    """
    resolved = resolve_redis_url(url)
    key = (resolved, decode_responses, socket_timeout)

    client = _clients.get(key)
    if client is not None:
        return client

    with _lock:
        client = _clients.get(key)
        if client is not None:
            return client
        client = Redis.from_url(
            resolved,
            decode_responses=decode_responses,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
        )
        _clients[key] = client
        logger.debug(
            "Created Redis client for %s (decode_responses=%s, timeout=%.1fs)",
            resolved,
            decode_responses,
            socket_timeout,
        )
        return client


def reset_redis_clients() -> None:
    """Drop every cached client, closing its pool. For tests and shutdown hooks."""
    with _lock:
        for client in _clients.values():
            try:
                client.close()
            except Exception:
                logger.exception("Error closing a cached Redis client")
        _clients.clear()
