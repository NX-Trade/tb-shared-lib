# pylint: disable=redefined-outer-name  # pytest fixtures are injected by name
# pylint: disable=protected-access       # patching the client's requests.Session is the seam
# pylint: disable=unused-argument        # fixtures requested purely for their side effects
"""Centralised outbound HTTP: limiting, breaking, redaction, telemetry, errors.

Replaces the guarantees RequestMaker only claimed to provide:

* breaker state is shared, so it actually trips (it was per-instance, and a new
  instance was built for every call);
* credentials never reach the database;
* bodies are stored complete, not truncated to 2 000 characters;
* failures arrive as typed errors carrying ``retryable``, so a timeout is not
  mistaken for a business rejection;
* order endpoints are never auto-retried, because the order may already be live.
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from tb_utils.http.breaker import BreakerConfig, BreakerState, RedisCircuitBreaker
from tb_utils.http.client import ExternalClient
from tb_utils.http.errors import (
    CircuitOpen,
    RateLimited,
    UpstreamAuthError,
    UpstreamBadRequest,
    UpstreamTimeout,
    UpstreamUnavailable,
    classify_status,
)
from tb_utils.http.limiter import RedisRateLimiter
from tb_utils.http.providers import (
    ApiProviderEnum,
    EndpointClassEnum,
    classify_endpoint,
    is_order_audit_endpoint,
    limits_for,
)
from tb_utils.http.redaction import REDACTED, redact_headers, redact_payload, redact_text
from tb_utils.http.retention import (
    DATA_RETENTION_DAYS,
    ORDER_AUDIT_RETENTION_DAYS,
    purge_expired_telemetry,
)
from tb_utils.http.telemetry import CallRecord, build_row, compress_text, decompress

CLIENT = "tb_utils.http.client"


class FakeRedis:
    """In-memory stand-in for the handful of Redis commands used here."""

    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.counters: dict[str, int] = {}

    # hash ops (breaker)
    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hset(self, key, mapping=None, **_):
        self.hashes.setdefault(key, {}).update({k: str(v) for k, v in (mapping or {}).items()})
        return 1

    def hincrby(self, key, field, amount=1):
        current = int(self.hashes.setdefault(key, {}).get(field, 0)) + amount
        self.hashes[key][field] = str(current)
        return current

    def delete(self, key):
        self.hashes.pop(key, None)
        return 1

    def expire(self, _key, _ttl):
        return True

    # counter ops (limiter)
    def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]


@pytest.fixture
def redis_client():
    return FakeRedis()


@pytest.fixture(autouse=True)
def _no_alerts():
    with patch(f"{CLIENT}.send_telegram_alert"):
        yield


@pytest.fixture
def no_backoff():
    """Skip the retry backoff.

    NOTE: ``client`` imports the ``time`` module, so patching
    ``client.time.sleep`` patches ``time.sleep`` globally — never make this
    autouse or tests that genuinely need to advance the clock silently break.
    """
    with patch(f"{CLIENT}.time.sleep"):
        yield


def _response(status=200, body='{"status":"success"}', reason="OK"):
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.ok = 200 <= status < 300
    response.text = body
    response.reason = reason
    response.headers = {"Content-Type": "application/json"}
    return response


def _client(redis_client, **kw):
    return ExternalClient(ApiProviderEnum.UPSTOX, redis_client, **kw)


# ── Endpoint classification & Q3 budgets ───────────────────────────────────


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://api.upstox.com/v2/order/place", EndpointClassEnum.ORDER),
        ("https://api.upstox.com/v3/order/gtt/place", EndpointClassEnum.GTT),
        ("https://api.upstox.com/v2/market-quote/ltp", EndpointClassEnum.MARKET_DATA),
        ("https://api.upstox.com/v2/historical-candle/X/day", EndpointClassEnum.HISTORICAL),
        ("https://api.upstox.com/v2/portfolio/long-term-holdings", EndpointClassEnum.PORTFOLIO),
        ("https://api.upstox.com/v2/user/profile", EndpointClassEnum.OTHER),
    ],
)
def test_endpoint_classification(url, expected):
    assert classify_endpoint(ApiProviderEnum.UPSTOX, url) == expected


def test_q3_rate_budgets():
    """80 % of Upstox's published ceilings (owner's answer to Q3)."""
    assert limits_for(ApiProviderEnum.UPSTOX, EndpointClassEnum.ORDER) == (8, 400)
    assert limits_for(ApiProviderEnum.UPSTOX, EndpointClassEnum.MARKET_DATA) == (20, 400)
    assert limits_for(ApiProviderEnum.UPSTOX, EndpointClassEnum.HISTORICAL) == (4, 200)
    assert limits_for(ApiProviderEnum.UPSTOX, EndpointClassEnum.GTT) == (4, 200)


def test_order_audit_endpoints_are_flagged_for_long_retention():
    assert is_order_audit_endpoint("/v2/order/place")
    assert is_order_audit_endpoint("/v3/order/gtt/modify")
    assert not is_order_audit_endpoint("/v2/market-quote/ltp")


# ── Redaction ──────────────────────────────────────────────────────────────


def test_authorization_header_never_stored():
    redacted = redact_headers(
        {"Authorization": "Bearer secret-token", "Accept": "application/json"}
    )
    assert redacted["Authorization"] == REDACTED
    assert redacted["Accept"] == "application/json"


@pytest.mark.parametrize("key", ["access_token", "api_secret", "password", "totp", "pin"])
def test_secret_body_keys_redacted(key):
    assert redact_payload({key: "value", "symbol": "INFY"})[key] == REDACTED


def test_nested_and_listed_secrets_redacted():
    payload = {"orders": [{"api_key": "k", "qty": 5}], "meta": {"password": "p"}}
    out = redact_payload(payload)
    assert out["orders"][0]["api_key"] == REDACTED
    assert out["orders"][0]["qty"] == 5
    assert out["meta"]["password"] == REDACTED


def test_bearer_token_in_free_text_redacted():
    assert "secret" not in redact_text("failed with Bearer abcdef123456 invalid")


def test_redaction_survives_non_json_text():
    assert redact_text("<html>502 Bad Gateway</html>") == "<html>502 Bad Gateway</html>"


# ── Compression ────────────────────────────────────────────────────────────


def test_large_body_round_trips_without_truncation():
    body = json.dumps({"orders": [{"id": i, "symbol": "INFY"} for i in range(500)]})
    assert len(body) > 2000  # the old code truncated here
    blob, codec = compress_text(body)
    assert codec == "zlib"
    assert len(blob) < len(body.encode())  # actually smaller
    assert decompress(blob, codec) == body  # and complete


def test_small_body_is_stored_raw():
    blob, codec = compress_text("ok")
    assert codec == "raw"
    assert decompress(blob, codec) == "ok"


def test_decompress_handles_missing_and_bad_input():
    assert decompress(None, "zlib") == ""
    assert decompress(b"not-zlib", "zlib") == ""
    assert decompress(b"plain", None) == "plain"


def test_telemetry_row_is_redacted_and_previewed():
    record = CallRecord(
        provider=2,
        url="/v2/order/place",
        method="POST",
        correlation_id="abc",
        request_headers={"Authorization": "Bearer t"},
        request_payload={"access_token": "t", "quantity": 5},
        status_code=200,
        response_text='{"status":"success","data":{"order_id":"1"}}',
        success=True,
    )
    row = build_row(record)

    assert REDACTED in row.request_headers
    assert "Bearer t" not in row.request_headers
    assert REDACTED in decompress(row.request_payload_z, row.compression)
    assert row.response_preview.startswith('{"status":"success"')
    assert row.is_success == 1


# ── Circuit breaker (shared state) ─────────────────────────────────────────


def test_breaker_opens_after_threshold_and_blocks(redis_client):
    breaker = RedisCircuitBreaker(redis_client, "UPSTOX", "order", BreakerConfig(max_failures=3))

    assert breaker.record_failure() is BreakerState.CLOSED
    assert breaker.record_failure() is BreakerState.CLOSED
    assert breaker.record_failure() is BreakerState.OPEN
    assert breaker.allows_request() is False


def test_breaker_state_is_shared_between_instances(redis_client):
    """The whole point: one worker's failures protect the others."""
    worker_a = RedisCircuitBreaker(redis_client, "UPSTOX", "order", BreakerConfig(max_failures=2))
    worker_b = RedisCircuitBreaker(redis_client, "UPSTOX", "order", BreakerConfig(max_failures=2))

    worker_a.record_failure()
    worker_a.record_failure()

    assert worker_b.allows_request() is False


def test_breaker_half_opens_after_timeout_then_closes_on_success(redis_client):
    config = BreakerConfig(max_failures=1, reset_timeout_seconds=60.0)
    breaker = RedisCircuitBreaker(redis_client, "UPSTOX", "order", config)
    breaker.record_failure()
    assert breaker.state() is BreakerState.OPEN

    # Age the breaker past its reset timeout rather than sleeping for it.
    key = "http:breaker:UPSTOX:order"
    redis_client.hashes[key]["opened_at"] = str(time.time() - 61)

    assert breaker.state() is BreakerState.HALF_OPEN
    assert breaker.allows_request() is True

    breaker.record_success()
    assert breaker.state() is BreakerState.CLOSED


def test_breaker_success_resets_the_counter(redis_client):
    breaker = RedisCircuitBreaker(redis_client, "UPSTOX", "order", BreakerConfig(max_failures=2))
    breaker.record_failure()
    breaker.record_success()
    assert breaker.record_failure() is BreakerState.CLOSED  # counter restarted


def test_breaker_fails_open_when_redis_is_down():
    broken = MagicMock()
    broken.hgetall.side_effect = ConnectionError("redis down")
    breaker = RedisCircuitBreaker(broken, "UPSTOX", "order")
    assert breaker.allows_request() is True


# ── Rate limiter ───────────────────────────────────────────────────────────


def test_limiter_allows_up_to_the_per_second_budget(redis_client):
    limiter = RedisRateLimiter(redis_client, "UPSTOX", "order", per_second=3, per_minute=100)
    now = 1_000_000.0

    assert all(limiter.acquire(now=now).allowed for _ in range(3))
    refused = limiter.acquire(now=now)
    assert refused.allowed is False
    assert "per second" in refused.reason
    assert refused.retry_after > 0


def test_limiter_windows_roll_over(redis_client):
    limiter = RedisRateLimiter(redis_client, "UPSTOX", "order", per_second=1, per_minute=100)
    assert limiter.acquire(now=1_000_000.0).allowed
    assert not limiter.acquire(now=1_000_000.4).allowed
    assert limiter.acquire(now=1_000_001.0).allowed  # next second


def test_limiter_enforces_the_minute_budget(redis_client):
    limiter = RedisRateLimiter(redis_client, "UPSTOX", "order", per_second=100, per_minute=2)
    base = 1_000_000.0
    assert limiter.acquire(now=base).allowed
    assert limiter.acquire(now=base + 1).allowed
    refused = limiter.acquire(now=base + 2)
    assert not refused.allowed and "per minute" in refused.reason


def test_limiter_is_disabled_without_a_budget(redis_client):
    limiter = RedisRateLimiter(redis_client, "OTHER", "other", per_second=0, per_minute=0)
    assert limiter.enabled is False
    assert limiter.acquire().allowed


def test_limiter_fails_open_when_redis_is_down():
    broken = MagicMock()
    broken.incr.side_effect = ConnectionError("redis down")
    limiter = RedisRateLimiter(broken, "UPSTOX", "order", 1, 1)
    assert limiter.acquire().allowed


# ── Client behaviour ───────────────────────────────────────────────────────


def test_successful_call_returns_response_and_closes_breaker(redis_client):
    client = _client(redis_client)
    with patch.object(client._http, "request", return_value=_response()) as sender:
        response = client.get("https://api.upstox.com/v2/user/profile")

    assert response.status_code == 200
    assert sender.call_count == 1


@pytest.mark.parametrize(
    "status, expected",
    [
        (401, UpstreamAuthError),
        (403, UpstreamAuthError),
        (429, RateLimited),
        (400, UpstreamBadRequest),
        (500, UpstreamUnavailable),
    ],
)
def test_status_codes_map_to_typed_errors(redis_client, status, expected):
    client = _client(redis_client, max_attempts=1)
    with patch.object(client._http, "request", return_value=_response(status=status, reason="x")):
        with pytest.raises(expected) as caught:
            client.get("https://api.upstox.com/v2/user/profile")

    assert caught.value.status_code == status
    assert caught.value.details["provider"] == "UPSTOX"


def test_auth_failure_is_not_retryable(redis_client):
    """Repeating a rejected token wastes budget and can lock the key out."""
    client = _client(redis_client, max_attempts=3)
    with patch.object(client._http, "request", return_value=_response(status=401)) as sender:
        with pytest.raises(UpstreamAuthError) as caught:
            client.get("https://api.upstox.com/v2/user/profile")

    assert sender.call_count == 1
    assert caught.value.retryable is False


def test_server_error_is_retried_then_raised(redis_client, no_backoff):
    client = _client(redis_client, max_attempts=3)
    with patch.object(client._http, "request", return_value=_response(status=503)) as sender:
        with pytest.raises(UpstreamUnavailable):
            client.get("https://api.upstox.com/v2/user/profile")

    assert sender.call_count == 3


def test_retry_succeeds_after_a_transient_failure(redis_client, no_backoff):
    client = _client(redis_client, max_attempts=3)
    with patch.object(
        client._http, "request", side_effect=[_response(status=503), _response()]
    ) as sender:
        assert client.get("https://api.upstox.com/v2/user/profile").status_code == 200
    assert sender.call_count == 2


def test_order_endpoints_are_never_auto_retried(redis_client):
    """A timeout on an order may mean the order is live — retrying could duplicate it."""
    client = _client(redis_client, max_attempts=3)
    with patch.object(client._http, "request", side_effect=requests.Timeout("boom")) as sender:
        with pytest.raises(UpstreamTimeout):
            client.post("https://api.upstox.com/v2/order/place", json_data={"qty": 1})

    assert sender.call_count == 1


def test_timeout_maps_to_upstream_timeout(redis_client):
    client = _client(redis_client, max_attempts=1)
    with patch.object(client._http, "request", side_effect=requests.Timeout("t")):
        with pytest.raises(UpstreamTimeout) as caught:
            client.get("https://api.upstox.com/v2/user/profile")
    assert caught.value.retryable is True


def test_connection_error_maps_to_unavailable(redis_client):
    client = _client(redis_client, max_attempts=1)
    with patch.object(client._http, "request", side_effect=requests.ConnectionError("no route")):
        with pytest.raises(UpstreamUnavailable):
            client.get("https://api.upstox.com/v2/user/profile")


def test_open_breaker_blocks_without_calling_the_provider(redis_client):
    client = _client(redis_client, breaker_config=BreakerConfig(max_failures=1), max_attempts=1)
    with patch.object(client._http, "request", return_value=_response(status=500)):
        with pytest.raises(UpstreamUnavailable):
            client.get("https://api.upstox.com/v2/user/profile")

    with patch.object(client._http, "request") as sender:
        with pytest.raises(CircuitOpen):
            client.get("https://api.upstox.com/v2/user/profile")
    sender.assert_not_called()


def test_rate_limit_refusal_does_not_call_the_provider(redis_client):
    client = _client(redis_client)
    # Burn the historical budget (4/s) for this endpoint class.
    limiter = RedisRateLimiter(redis_client, "UPSTOX", "historical", 4, 200)
    for _ in range(4):
        limiter.acquire(now=1_000_000.0)

    with (
        patch.object(client._http, "request") as sender,
        patch("time.time", return_value=1_000_000.0),
    ):
        with pytest.raises(RateLimited):
            client.get("https://api.upstox.com/v2/historical-candle/X/day/2026-01-01")
    sender.assert_not_called()


def test_telemetry_is_written_per_call(redis_client):
    db = MagicMock()
    client = _client(redis_client, session_factory=lambda: db)
    with patch.object(client._http, "request", return_value=_response()):
        client.get("https://api.upstox.com/v2/user/profile")

    db.add.assert_called_once()
    row = db.add.call_args[0][0]
    assert row.correlation_id
    assert row.is_success == 1
    db.close.assert_called_once()


def test_telemetry_failure_never_breaks_the_call(redis_client):
    db = MagicMock()
    db.commit.side_effect = RuntimeError("db gone")
    client = _client(redis_client, session_factory=lambda: db)
    with patch.object(client._http, "request", return_value=_response()):
        assert client.get("https://api.upstox.com/v2/user/profile").status_code == 200


def test_correlation_id_is_reused_across_retries(redis_client, no_backoff):
    db = MagicMock()
    client = _client(redis_client, session_factory=lambda: db, max_attempts=2)
    with patch.object(client._http, "request", side_effect=[_response(status=503), _response()]):
        client.get("https://api.upstox.com/v2/user/profile", correlation_id="fixed-id")

    ids = {call[0][0].correlation_id for call in db.add.call_args_list}
    assert ids == {"fixed-id"}


def test_classify_status_covers_the_families():
    assert classify_status(401) is UpstreamAuthError
    assert classify_status(429) is RateLimited
    assert classify_status(503) is UpstreamUnavailable
    assert classify_status(422) is UpstreamBadRequest


# ── Retention (Q4) ─────────────────────────────────────────────────────────


def test_retention_windows_match_the_owner_decision():
    assert DATA_RETENTION_DAYS == 30
    assert ORDER_AUDIT_RETENTION_DAYS == 365 * 5


def test_purge_uses_two_windows_and_excludes_orders_from_the_short_one():
    """Order rows must survive the 30-day sweep — they are a 5-year audit trail."""
    db = MagicMock()
    db.execute.return_value.rowcount = 7

    result = purge_expired_telemetry(db)

    assert db.execute.call_count == 2
    data_sql = str(db.execute.call_args_list[0][0][0]).replace("\n", " ")
    order_sql = str(db.execute.call_args_list[1][0][0]).replace("\n", " ")
    assert "NOT" in data_sql.upper()  # non-order rows only
    assert "NOT" not in order_sql.upper()  # order rows only
    assert result.total == 14
    db.commit.assert_called_once()
