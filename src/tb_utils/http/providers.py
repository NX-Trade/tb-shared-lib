"""Third-party API providers, their rate limits and retention classes.

Limits are set to ~80 % of each provider's published ceiling so bursts (a
liquidation sweeping several positions at once) stay inside the real limit.
Values come from the owner's answers in review 13 (Q3).

Endpoint *classes* matter because providers publish per-class limits: order
placement and historical data are metered separately. The client classifies a
URL once and applies that class's bucket.
"""

from enum import IntEnum, StrEnum


class ApiProviderEnum(IntEnum):
    """Stable ids written to ``external_api_request.api_provider``.

    Integers (not names) because the column is an int; existing rows used 2 for
    Upstox, so that value is preserved.
    """

    NSE = 1
    UPSTOX = 2
    OLLAMA = 3
    TELEGRAM = 4
    GEMINI = 5


class EndpointClassEnum(StrEnum):
    """Rate-limit class of an endpoint."""

    ORDER = "order"
    MARKET_DATA = "market_data"
    HISTORICAL = "historical"
    GTT = "gtt"
    PORTFOLIO = "portfolio"
    OTHER = "other"


# (per_second, per_minute) — 80 % of published limits. None = unmetered by us.
PROVIDER_LIMITS: dict[ApiProviderEnum, dict[EndpointClassEnum, tuple[int, int]]] = {
    ApiProviderEnum.UPSTOX: {
        # Published: order 10/s & 500/min, quotes 25/s & 500/min,
        # historical 5/s, GTT 5/s, portfolio 10/s.
        EndpointClassEnum.ORDER: (8, 400),
        EndpointClassEnum.MARKET_DATA: (20, 400),
        EndpointClassEnum.HISTORICAL: (4, 200),
        EndpointClassEnum.GTT: (4, 200),
        EndpointClassEnum.PORTFOLIO: (8, 400),
        EndpointClassEnum.OTHER: (8, 400),
    },
    ApiProviderEnum.NSE: {
        # NSE publishes nothing; this is the scrape-politeness budget the
        # collector already used (10/s).
        EndpointClassEnum.OTHER: (8, 240),
    },
}

# Substrings that identify an endpoint's class. Checked in order, first match
# wins, so more specific fragments must come first.
_UPSTOX_ENDPOINT_CLASSES: tuple[tuple[str, EndpointClassEnum], ...] = (
    ("/order/rules", EndpointClassEnum.GTT),
    ("/gtt", EndpointClassEnum.GTT),
    ("/historical-candle", EndpointClassEnum.HISTORICAL),
    ("/order", EndpointClassEnum.ORDER),
    ("/trade", EndpointClassEnum.ORDER),
    ("/portfolio", EndpointClassEnum.PORTFOLIO),
    ("/positions", EndpointClassEnum.PORTFOLIO),
    ("/holdings", EndpointClassEnum.PORTFOLIO),
    ("/market-quote", EndpointClassEnum.MARKET_DATA),
    ("/ltp", EndpointClassEnum.MARKET_DATA),
    ("/option/chain", EndpointClassEnum.MARKET_DATA),
)

# Endpoint fragments whose telemetry is an execution audit record. These are
# retained for years, not days (review 13, Q4): they evidence what was sent to
# the exchange on our behalf.
ORDER_AUDIT_FRAGMENTS: tuple[str, ...] = ("/order", "/gtt", "/trade")


def classify_endpoint(provider: ApiProviderEnum, url: str) -> EndpointClassEnum:
    """Return the rate-limit class for ``url``."""
    if provider != ApiProviderEnum.UPSTOX:
        return EndpointClassEnum.OTHER
    lowered = url.lower()
    for fragment, endpoint_class in _UPSTOX_ENDPOINT_CLASSES:
        if fragment in lowered:
            return endpoint_class
    return EndpointClassEnum.OTHER


def limits_for(provider: ApiProviderEnum, endpoint_class: EndpointClassEnum) -> tuple[int, int]:
    """Return ``(per_second, per_minute)`` for a provider/class, ``(0, 0)`` if unmetered."""
    provider_limits = PROVIDER_LIMITS.get(provider)
    if not provider_limits:
        return (0, 0)
    return provider_limits.get(endpoint_class) or provider_limits.get(
        EndpointClassEnum.OTHER, (0, 0)
    )


def is_order_audit_endpoint(url: str) -> bool:
    """True when this call must be kept for the long (regulatory) retention."""
    lowered = url.lower()
    return any(fragment in lowered for fragment in ORDER_AUDIT_FRAGMENTS)
