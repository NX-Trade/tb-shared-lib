"""One Redis client factory, one connection pool per configuration.

There were 39 `Redis.from_url(...)` sites across the services. Each call builds a
new ConnectionPool, and the ones inside functions (the Upstox adapter, the
trading-halt check) built a fresh pool on *every invocation*. Decoding was also
inconsistent: most sites passed decode_responses=True, a few did not, so the same
key returned str through one module and bytes through another.
"""

import os
from unittest.mock import patch

from tb_utils.redis.client import (
    DEFAULT_URL,
    get_redis,
    reset_redis_clients,
    resolve_redis_url,
)

URL = "redis://localhost:6379/15"


def setup_function():
    reset_redis_clients()


def teardown_function():
    reset_redis_clients()


# ── URL resolution ─────────────────────────────────────────────────────────


def test_explicit_url_wins():
    assert resolve_redis_url(URL) == URL


def test_redis_url_env_is_preferred_over_celery_broker():
    with patch.dict(os.environ, {"REDIS_URL": "redis://a:1", "CELERY_BROKER_URL": "redis://b:2"}):
        assert resolve_redis_url() == "redis://a:1"


def test_celery_broker_url_is_the_fallback():
    with patch.dict(os.environ, {"CELERY_BROKER_URL": "redis://b:2"}, clear=True):
        assert resolve_redis_url() == "redis://b:2"


def test_default_when_nothing_is_configured():
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_redis_url() == DEFAULT_URL


# ── Pool sharing ───────────────────────────────────────────────────────────


def test_same_configuration_reuses_one_client_and_pool():
    first = get_redis(URL)
    second = get_redis(URL)

    assert first is second
    assert first.connection_pool is second.connection_pool


def test_repeated_calls_do_not_leak_pools():
    """The pattern that mattered: a client built inside a hot function."""
    pools = {id(get_redis(URL).connection_pool) for _ in range(50)}
    assert len(pools) == 1


def test_decode_mode_yields_distinct_clients():
    text = get_redis(URL)
    raw = get_redis(URL, decode_responses=False)

    assert text is not raw
    assert text.connection_pool.connection_kwargs["decode_responses"] is True
    assert raw.connection_pool.connection_kwargs["decode_responses"] is False


def test_different_urls_are_not_shared():
    assert get_redis("redis://localhost:6379/1") is not get_redis("redis://localhost:6379/2")


# ── Defaults ───────────────────────────────────────────────────────────────


def test_decoding_defaults_to_text():
    """Most existing callers assume str, so that is the default."""
    kwargs = get_redis(URL).connection_pool.connection_kwargs
    assert kwargs["decode_responses"] is True


def test_timeouts_are_set_on_both_connect_and_read():
    """Every caller is on a latency-sensitive path; a hung Redis must fail fast."""
    kwargs = get_redis(URL).connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == 2.0
    assert kwargs["socket_connect_timeout"] == 2.0


def test_custom_timeout_is_honoured_and_cached_separately():
    slow = get_redis(URL, socket_timeout=10.0)
    assert slow.connection_pool.connection_kwargs["socket_timeout"] == 10.0
    assert slow is not get_redis(URL)


def test_construction_does_not_require_a_live_server():
    """from_url is lazy — an unreachable server must not raise here."""
    assert get_redis("redis://192.0.2.1:6379/0") is not None


def test_reset_clears_the_cache():
    first = get_redis(URL)
    reset_redis_clients()
    assert get_redis(URL) is not first
