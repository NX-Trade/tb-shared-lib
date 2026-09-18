"""Typed errors for outbound HTTP calls.

Callers need to tell apart "the venue said no" (never retry — it is a business
decision) from "we could not ask" (retry, or degrade). Before this, every
failure arrived as a bare ``requests.RequestException`` or was flattened into a
rejected order result, so a 3-second timeout and a genuine margin rejection were
indistinguishable and both got marked permanently REJECTED.

Every error carries:

``code``       stable machine-readable string for logs, metrics and tests
``retryable``  whether the same call may reasonably be attempted again
``alert``      whether a human should be told now
``details``    structured context (provider, endpoint, status, correlation id)

This hierarchy is the seed of the service-wide typed exception work: it lives
here so tb-execution, tb-collector and tb-signal-bot share one root.
"""

from typing import Any, Optional


class NxTradeError(Exception):
    """Root of every deliberate error raised by nx-trade code."""

    code: str = "NX_ERROR"
    retryable: bool = False
    alert: bool = False

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details

    def __str__(self) -> str:
        if not self.details:
            return self.message
        context = " ".join(f"{k}={v}" for k, v in self.details.items() if v is not None)
        return f"{self.message} ({context})" if context else self.message


class ExternalApiError(NxTradeError):
    """Base for any failure talking to a third-party API.

    The well-known context fields are promoted to attributes (as well as being
    kept in ``details``) so callers can branch on them without dictionary
    lookups: ``if exc.status_code == 429`` reads better than
    ``exc.details.get("status_code")``.
    """

    code = "EXTERNAL_API_ERROR"

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        endpoint: str = "",
        status_code: Optional[int] = None,
        correlation_id: str = "",
        **details: Any,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            endpoint=endpoint,
            status_code=status_code,
            correlation_id=correlation_id,
            **details,
        )
        self.provider = provider
        self.endpoint = endpoint
        self.status_code = status_code
        self.correlation_id = correlation_id


class CircuitOpen(ExternalApiError):
    """The breaker for this provider is open — the call was not attempted.

    Not retryable *right now*: the point of the breaker is to stop hammering a
    failing dependency. Callers should degrade (skip the enrichment, fall back
    to the deterministic path) rather than loop.
    """

    code = "CIRCUIT_OPEN"
    retryable = False
    alert = False  # opening the breaker already alerted


class RateLimited(ExternalApiError):
    """Our own limiter, or the provider's 429, refused the call."""

    code = "RATE_LIMITED"
    retryable = True

    def __init__(
        self, message: str, *, retry_after: Optional[float] = None, **details: Any
    ) -> None:
        super().__init__(message, retry_after=retry_after, **details)
        self.retry_after = retry_after


class UpstreamTimeout(ExternalApiError):
    """No response within the timeout. The request may still have been executed.

    For order placement this is the dangerous case: never assume the order was
    rejected — reconcile before resubmitting.
    """

    code = "UPSTREAM_TIMEOUT"
    retryable = True
    alert = True


class UpstreamUnavailable(ExternalApiError):
    """Connection refused/reset, DNS failure, or a 5xx from the provider."""

    code = "UPSTREAM_UNAVAILABLE"
    retryable = True
    alert = True


class UpstreamAuthError(ExternalApiError):
    """401/403 — the token is missing, expired or lacks permission.

    Retrying with the same credentials cannot help; the token must be refreshed.
    """

    code = "UPSTREAM_AUTH"
    retryable = False
    alert = True


class UpstreamBadRequest(ExternalApiError):
    """4xx that is our fault (malformed payload, unknown instrument).

    Not retryable — the same request will fail identically.
    """

    code = "UPSTREAM_BAD_REQUEST"
    retryable = False


class UpstreamBadResponse(ExternalApiError):
    """HTTP 200 whose body could not be parsed as the expected shape."""

    code = "UPSTREAM_BAD_RESPONSE"
    retryable = False
    alert = True


def classify_status(status_code: int) -> type[ExternalApiError]:
    """Map an HTTP status onto the error type that describes it."""
    if status_code in (401, 403):
        return UpstreamAuthError
    if status_code == 429:
        return RateLimited
    if 500 <= status_code < 600:
        return UpstreamUnavailable
    return UpstreamBadRequest
