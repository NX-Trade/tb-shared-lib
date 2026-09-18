"""Centralised outbound HTTP: rate limiting, circuit breaking, telemetry.

Every third-party call should go through :class:`ExternalClient` so that rate
budgets, breaker state and audit telemetry are shared across all workers rather
than reinvented (and kept per-process) by each caller.
"""

from tb_utils.http.breaker import BreakerConfig, BreakerState, RedisCircuitBreaker
from tb_utils.http.client import ExternalClient
from tb_utils.http.errors import (
    CircuitOpen,
    ExternalApiError,
    NxTradeError,
    RateLimited,
    UpstreamAuthError,
    UpstreamBadRequest,
    UpstreamBadResponse,
    UpstreamTimeout,
    UpstreamUnavailable,
    classify_status,
)
from tb_utils.http.limiter import LimitDecision, RedisRateLimiter
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
    PurgeResult,
    purge_expired_telemetry,
)
from tb_utils.http.telemetry import CallRecord, compress_text, decompress

__all__ = [
    "ApiProviderEnum",
    "BreakerConfig",
    "BreakerState",
    "CallRecord",
    "DATA_RETENTION_DAYS",
    "CircuitOpen",
    "EndpointClassEnum",
    "ExternalApiError",
    "ExternalClient",
    "LimitDecision",
    "NxTradeError",
    "ORDER_AUDIT_RETENTION_DAYS",
    "PurgeResult",
    "purge_expired_telemetry",
    "RateLimited",
    "REDACTED",
    "RedisCircuitBreaker",
    "RedisRateLimiter",
    "UpstreamAuthError",
    "UpstreamBadRequest",
    "UpstreamBadResponse",
    "UpstreamTimeout",
    "UpstreamUnavailable",
    "classify_endpoint",
    "classify_status",
    "compress_text",
    "decompress",
    "is_order_audit_endpoint",
    "limits_for",
    "redact_headers",
    "redact_payload",
    "redact_text",
]
