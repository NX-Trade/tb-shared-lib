"""The hand-off of an on-demand option chain between the collector and the trade path.

The periodic collector run refreshes every F&O chain every 15 minutes and keeps it for six hours.
That suits dashboards and is wrong for pricing an order. For a trade decision the collector is asked
to fetch **one underlying now** and writes the result here; the trade path loads it as a
:class:`FreshChain`, which only exists if the snapshot was fetched at or after the moment the
decision asked for it.

One module owns the format so the writer (collector) and the reader (trade engine) cannot drift. No
network and no database: it takes a Redis client and returns plain values, so it is tested with a
fake.

The payload is deliberately small: only what the spread engine reads (prices, open interest, volume,
IV, spot). Lot size and tick belong to the caller, because they come from the instrument master and
not from a chain.
"""

import datetime as dt
import json
from typing import Any, Optional

from tb_utils.options.ideas import ChainData, Quote
from tb_utils.options.spread_types import FreshChain
from tb_utils.redis.keys import get_fresh_chain_key

# Long enough to be read once the refresh finishes, short enough that an old one is never reused.
FRESH_CHAIN_TTL_SECONDS = 300


class ChainUnavailable(Exception):
    """No usable on-demand snapshot for the symbol: never fetched, expired or unreadable."""


def fresh_record(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    expiry: dt.date,
    strike: float,
    option_type: str,
    bid: Optional[float],
    ask: Optional[float],
    ltp: Optional[float],
    open_interest: int,
    volume: int,
    iv: Optional[float],
) -> dict[str, Any]:
    """One contract in the compact wire format."""
    return {
        "e": expiry.isoformat(), "k": float(strike), "t": option_type, "b": bid, "a": ask,
        "l": ltp, "oi": int(open_interest or 0), "v": int(volume or 0), "iv": iv,
    }  # fmt: skip


def build_payload(
    symbol: str,
    spot: float,
    records: list[dict[str, Any]],
    requested_at: dt.datetime,
    fetched_at: dt.datetime,
) -> dict[str, Any]:
    """The snapshot to store: what was asked for, when it was fetched, and the quotes."""
    return {
        "symbol": symbol.strip().upper(),
        "requested_at": requested_at.isoformat(),
        "fetched_at": fetched_at.isoformat(),
        "spot": spot,
        "records": records,
    }


def store_fresh_chain(redis_client: Any, symbol: str, payload: dict[str, Any]) -> None:
    redis_client.setex(get_fresh_chain_key(symbol), FRESH_CHAIN_TTL_SECONDS, json.dumps(payload))


def read_payload(redis_client: Any, symbol: str) -> Optional[dict[str, Any]]:
    """The stored snapshot as written, or None. Freshness is judged by :func:`load_fresh_chain`."""
    raw = redis_client.get(get_fresh_chain_key(symbol))
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _positive(value: Any) -> Optional[float]:
    """A price or volatility, or None when it is missing or zero (unpriced), never a fake 0."""
    return float(value) if value not in (None, 0, 0.0) and float(value) > 0 else None


def _quote(record: dict[str, Any]) -> Quote:
    return Quote(
        expiry=dt.date.fromisoformat(record["e"]),
        strike=float(record["k"]),
        option_type=record["t"],
        bid=_positive(record.get("b")),
        ask=_positive(record.get("a")),
        ltp=_positive(record.get("l")),
        open_interest=int(record.get("oi") or 0),
        volume=int(record.get("v") or 0),
        iv=_positive(record.get("iv")),
    )


def load_fresh_chain(
    redis_client: Any,
    symbol: str,
    requested_at: dt.datetime,
    lot_size: int,
    is_index: bool = False,
) -> FreshChain:
    """The snapshot as a :class:`FreshChain`, or an exception saying why there is none.

    Raises :class:`ChainUnavailable` when nothing usable is stored and
    :class:`~tb_utils.options.spread_types.StaleChainError` when what is stored was fetched before
    ``requested_at`` (another decision's refresh, say): it cannot vouch for this one.
    """
    payload = read_payload(redis_client, symbol)
    if payload is None:
        raise ChainUnavailable(f"no fresh chain is stored for {symbol.strip().upper()}")
    try:
        fetched_at = dt.datetime.fromisoformat(payload["fetched_at"])
        spot = float(payload["spot"])
        records = payload["records"]
        quotes = [_quote(r) for r in records]
    except (KeyError, TypeError, ValueError) as exc:
        raise ChainUnavailable(f"the stored chain for {symbol} is unreadable: {exc}") from exc
    if spot <= 0:
        raise ChainUnavailable(f"the stored chain for {symbol} has no spot price")
    if not quotes:
        raise ChainUnavailable(f"the stored chain for {symbol} has no quotes")
    chain = ChainData(symbol.strip().upper(), fetched_at, spot, lot_size, is_index, quotes)
    return FreshChain(chain, requested_at)  # raises StaleChainError if it predates the request


__all__ = [
    "FRESH_CHAIN_TTL_SECONDS",
    "ChainUnavailable",
    "build_payload",
    "fresh_record",
    "load_fresh_chain",
    "read_payload",
    "store_fresh_chain",
]
