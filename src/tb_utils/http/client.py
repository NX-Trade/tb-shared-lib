"""One way out of this codebase to any third-party HTTP API.

Every outbound call gets, in this order:

1. **Rate limiting** — shared fixed-window counters sized from the provider's
   published limits (80 % of them).
2. **Circuit breaking** — shared state in Redis, so all workers back off
   together instead of each discovering the outage separately.
3. **The request** — one ``requests.Session`` per client, explicit timeout.
4. **Retries** — only for errors whose type says ``retryable``, with
   exponential backoff. A timeout on an *order* endpoint is never retried
   automatically: the order may have reached the exchange, so resubmitting
   risks a duplicate. Reconcile instead.
5. **Typed errors** — callers branch on ``exc.retryable`` / ``exc.code``, never
   on message text.
6. **Telemetry** — compressed, redacted request/response persisted with a
   correlation id.

Replaces ``RequestMaker``, whose breaker state was per-instance (and a new
instance was built per call, so it never tripped), which stored live bearer
tokens in the clear and truncated bodies to 2 000 characters.
"""

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any, Optional

import requests
from redis import Redis
from sqlalchemy.orm import Session

from tb_utils.http.breaker import BreakerConfig, BreakerState, RedisCircuitBreaker
from tb_utils.http.errors import (
    CircuitOpen,
    ExternalApiError,
    RateLimited,
    UpstreamTimeout,
    UpstreamUnavailable,
    classify_status,
)
from tb_utils.http.limiter import RedisRateLimiter
from tb_utils.http.providers import (
    ApiProviderEnum,
    classify_endpoint,
    limits_for,
)
from tb_utils.http.telemetry import CallRecord, save
from tb_utils.telegram import send_telegram_alert

logger = logging.getLogger(__name__)


def _independent_session(factory: Any) -> Session:
    """Return a Session that is not shared with the caller.

    Accepts a ``scoped_session``, a ``sessionmaker``, or the lazy ``SessionLocal``
    proxy. For anything registry-backed, the underlying ``session_factory`` is
    used so the returned Session is genuinely new and safe to close.
    """
    underlying = getattr(factory, "session_factory", None)
    if underlying is not None:
        return underlying()
    return factory()


DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5

# Endpoint classes where an automatic retry could duplicate a side effect.
NON_IDEMPOTENT_CLASSES = frozenset({"order", "gtt"})


class ExternalClient:
    """HTTP client for one provider, with shared limiting, breaking and telemetry."""

    def __init__(
        self,
        provider: ApiProviderEnum,
        redis_client: Redis,
        session_factory: Optional[Any] = None,
        breaker_config: Optional[BreakerConfig] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        """
        Args:
            provider: Which third party this client talks to.
            redis_client: Shared Redis used for breaker and limiter state.
            session_factory: Callable returning a DB ``Session`` for telemetry.
                Omit to disable persistence (tests, scripts).
            breaker_config: Failure threshold and reset timeout.
            timeout: Per-request timeout in seconds.
            max_attempts: Total attempts for retryable failures.
        """
        self._provider = provider
        self._redis = redis_client
        self._session_factory = session_factory
        self._breaker_config = breaker_config or BreakerConfig()
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._http = requests.Session()

    # ── Public API ─────────────────────────────────────────────────────────

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        json_data: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        """Perform an HTTP request.

        Returns:
            The successful ``requests.Response`` (2xx).

        Raises:
            CircuitOpen: breaker open for this provider/endpoint class.
            RateLimited: our budget or the provider's 429 refused the call.
            UpstreamTimeout / UpstreamUnavailable / UpstreamAuthError /
            UpstreamBadRequest: mapped from the transport failure or status.
        """
        endpoint_class = classify_endpoint(self._provider, url)
        correlation_id = correlation_id or uuid.uuid4().hex
        breaker = self._breaker(endpoint_class)

        self._check_rate_limit(endpoint_class, url, correlation_id)
        self._check_breaker(breaker, endpoint_class, url, correlation_id)

        attempts = 1 if str(endpoint_class) in NON_IDEMPOTENT_CLASSES else self._max_attempts
        last_error: Optional[ExternalApiError] = None

        for attempt in range(1, attempts + 1):
            try:
                return self._attempt(
                    method,
                    url,
                    headers,
                    json_data,
                    params,
                    timeout,
                    correlation_id,
                    breaker,
                    attempt,
                )
            except ExternalApiError as exc:
                last_error = exc
                if not exc.retryable or attempt == attempts:
                    break
                delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "%s %s failed (%s) — retrying in %.1fs [%d/%d] correlation_id=%s",
                    method,
                    url,
                    exc.code,
                    delay,
                    attempt,
                    attempts,
                    correlation_id,
                )
                time.sleep(delay)

        assert last_error is not None  # loop always sets it before breaking
        raise last_error

    def guarded_call(
        self,
        fn: Callable[..., Any],
        *args: Any,
        endpoint: str,
        correlation_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Run a third-party SDK call under the same rate limit, breaker and telemetry.

        Some providers are reached through their own client library
        (``upstox_client``, the Ollama package, ``nselib``) which owns the socket,
        so :meth:`request` cannot be used. Those calls still consume the
        provider's rate budget and still deserve to trip the breaker, so wrap
        them here instead of leaving them unguarded.

        Unlike :meth:`request`, the original SDK exception is re-raised
        unchanged — callers already handle their library's error types, and
        guessing a mapping for every SDK would be worse than passing it through.
        The failure is still counted against the breaker and recorded.

        Args:
            fn: The SDK function to invoke.
            *args: Positional arguments for ``fn``.
            endpoint: Logical endpoint used for rate-limit classification and
                telemetry, e.g. ``"/v2/historical-candle"``.
            correlation_id: Optional id to correlate with related calls.
            **kwargs: Keyword arguments for ``fn``.

        Returns:
            Whatever ``fn`` returns.

        Raises:
            CircuitOpen: breaker open for this provider/endpoint class.
            RateLimited: our budget refused the call.
            Exception: any exception ``fn`` raised, unchanged.
        """
        endpoint_class = classify_endpoint(self._provider, endpoint)
        correlation_id = correlation_id or uuid.uuid4().hex
        breaker = self._breaker(endpoint_class)

        self._check_rate_limit(endpoint_class, endpoint, correlation_id)
        self._check_breaker(breaker, endpoint_class, endpoint, correlation_id)

        record = CallRecord(
            provider=int(self._provider),
            url=endpoint,
            method="SDK",
            correlation_id=correlation_id,
            breaker_state=int(breaker.state()),
        )
        started = time.time()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            self._finish_failure(record, started, breaker, type(exc).__name__, str(exc))
            raise

        record.duration_ms = int((time.time() - started) * 1000)
        record.success = True
        record.status_code = 200
        self._save(record)
        breaker.record_success()
        return result

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", url, **kwargs)

    # ── Gates ──────────────────────────────────────────────────────────────

    def _check_rate_limit(self, endpoint_class: str, url: str, correlation_id: str) -> None:
        per_second, per_minute = limits_for(self._provider, endpoint_class)
        limiter = RedisRateLimiter(
            self._redis, self._provider.name, str(endpoint_class), per_second, per_minute
        )
        decision = limiter.acquire()
        if decision.allowed:
            return
        logger.warning("Rate limit refused %s (correlation_id=%s)", url, correlation_id)
        raise RateLimited(
            decision.reason,
            retry_after=decision.retry_after,
            provider=self._provider.name,
            endpoint=url,
            correlation_id=correlation_id,
        )

    def _check_breaker(
        self, breaker: RedisCircuitBreaker, endpoint_class: str, url: str, correlation_id: str
    ) -> None:
        if breaker.allows_request():
            return
        raise CircuitOpen(
            f"Circuit breaker is OPEN for {self._provider.name}/{endpoint_class}",
            provider=self._provider.name,
            endpoint=url,
            correlation_id=correlation_id,
        )

    # ── One attempt ────────────────────────────────────────────────────────

    def _attempt(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]],
        json_data: Optional[dict[str, Any]],
        params: Optional[dict[str, Any]],
        timeout: Optional[float],
        correlation_id: str,
        breaker: RedisCircuitBreaker,
        attempt: int,
    ) -> requests.Response:
        record = CallRecord(
            provider=int(self._provider),
            url=url,
            method=method,
            correlation_id=correlation_id,
            request_headers=headers,
            request_payload=json_data if json_data is not None else params,
            retry_count=attempt - 1,
            breaker_state=int(breaker.state()),
        )
        started = time.time()

        try:
            response = self._http.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=timeout or self._timeout,
            )
        except requests.Timeout as exc:
            self._finish_failure(record, started, breaker, "timeout", str(exc))
            raise UpstreamTimeout(
                f"{method} {url} timed out",
                provider=self._provider.name,
                endpoint=url,
                correlation_id=correlation_id,
            ) from exc
        except requests.RequestException as exc:
            self._finish_failure(record, started, breaker, "transport", str(exc))
            raise UpstreamUnavailable(
                f"{method} {url} failed: {exc}",
                provider=self._provider.name,
                endpoint=url,
                correlation_id=correlation_id,
            ) from exc

        record.duration_ms = int((time.time() - started) * 1000)
        record.status_code = response.status_code
        record.response_headers = dict(response.headers)
        record.response_text = response.text or ""

        if response.ok:
            record.success = True
            self._save(record)
            breaker.record_success()
            return response

        record.error_code = str(response.status_code)
        record.error_message = (response.reason or "")[:500]
        self._save(record)
        self._on_failure(breaker)

        error_type = classify_status(response.status_code)
        raise error_type(
            f"{method} {url} returned {response.status_code}",
            provider=self._provider.name,
            endpoint=url,
            status_code=response.status_code,
            correlation_id=correlation_id,
            body=(record.response_text or "")[:200],
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _finish_failure(
        self,
        record: CallRecord,
        started: float,
        breaker: RedisCircuitBreaker,
        error_code: str,
        message: str,
    ) -> None:
        record.duration_ms = int((time.time() - started) * 1000)
        record.success = False
        record.error_code = error_code
        record.error_message = message[:500]
        self._save(record)
        self._on_failure(breaker)

    def _on_failure(self, breaker: RedisCircuitBreaker) -> None:
        """Count the failure and alert once on the CLOSED → OPEN edge."""
        if breaker.record_failure() is not BreakerState.OPEN:
            return
        try:
            send_telegram_alert(
                f"🔴 <b>Circuit Breaker OPEN</b>\n"
                f"<b>Provider:</b> {self._provider.name}\n"
                f"<b>Blocking for:</b> {self._breaker_config.reset_timeout_seconds:.0f}s"
            )
        except Exception:
            logger.exception("Failed to send circuit-breaker alert")

    def _breaker(self, endpoint_class: str) -> RedisCircuitBreaker:
        return RedisCircuitBreaker(
            self._redis, self._provider.name, str(endpoint_class), self._breaker_config
        )

    def _save(self, record: CallRecord) -> None:
        """Persist telemetry in a session of its own.

        Deliberately never uses the caller's session. ``SessionLocal`` and
        ``get_session_factory()`` are backed by a ``scoped_session``, so inside a
        single thread they return **the same Session** the caller is already
        using; closing it here would detach every ORM instance the caller had
        loaded. That is exactly what broke ``order_worker`` on 2026-09-18:

            DetachedInstanceError: Instance <TradingOrder ...> is not bound to a
            Session; attribute refresh operation cannot proceed

        A ``scoped_session`` is therefore unwrapped to its underlying factory to
        get an independent Session. Telemetry is a side channel — it must never
        be able to damage the transaction that triggered it.
        """
        if self._session_factory is None:
            return
        try:
            db: Session = _independent_session(self._session_factory)
        except Exception:
            logger.exception("Could not open a session for API telemetry")
            return
        try:
            save(db, record)
        finally:
            db.close()
