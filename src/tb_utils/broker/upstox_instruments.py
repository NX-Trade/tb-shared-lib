"""Upstox instrument master cache and key resolution.

Maintains a comprehensive mapping of NSE equities, indices, and F&O derivative
contracts from Upstox's daily instrument master feed
(``https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz``).

Upstox API v2 requires exact instrument keys:
- Equities: ``NSE_EQ|{isin}`` (e.g. ``NSE_EQ|INE742F01042``)
- Indices: ``NSE_INDEX|{name}`` (e.g. ``NSE_INDEX|Nifty 50``)
- F&O Contracts (Options & Futures): ``NSE_FO|{exchange_token}``
  (e.g. ``NSE_FO|81397`` for ``ADANIPORTS26SEP1800CE``, ``NSE_FO|56480`` for ``BAJAJ-AUTO26SEP11300PE``)

Sending an invalid key such as ``NSE_EQ|ADANIPORTS26SEP1800CE`` causes an HTTP 400
bad request which trips the provider circuit breaker and halts order placement
for all symbols. This module ensures derivative symbols are accurately resolved to
``NSE_FO|{token}`` and never erroneously formatted as ``NSE_EQ``.
"""

import datetime as dt
import gzip
import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Optional

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from tb_utils.config.apiconfig import UpstoxApiConfig
from tb_utils.models.instrument import Instrument
from tb_utils.utils.enums import InstrumentTypeEnum
from tb_utils.utils.symbol_parser import parse_trading_symbol

logger = logging.getLogger(__name__)

UPSTOX_NSE_INSTRUMENTS_URL: str = (
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
)
REDIS_KEY_UPSTOX_INSTRUMENTS: str = "market:upstox:instruments"

MONTH_NAMES: list[str] = [
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]

_IN_MEMORY_KEY_CACHE: dict[str, str] = {}


def build_upstox_lookup(items: list[dict[str, Any]]) -> dict[str, str]:
    """Parse Upstox instrument master items into a comprehensive symbol-to-key dictionary.

    Maps:
    - Raw trading_symbol (with and without spaces)
    - Underlying company name
    - ISIN
    - Standard NSE compact option format (``UNDERLYING + YY + MON + STRIKE + TYPE``)
    - Weekly option formats (with day and single-char month format)
    - Standard NSE futures format (``UNDERLYING + YY + MON + FUT``)

    Args:
        items: List of raw instrument dicts parsed from Upstox ``NSE.json.gz``.

    Returns:
        Dictionary mapping normalized symbol strings to ``instrument_key``.
    """
    lookup: dict[str, str] = {}

    for d in items:
        key = d.get("instrument_key")
        if not key:
            continue

        seg = d.get("segment")
        raw_ts = (d.get("trading_symbol") or "").upper().strip()
        name = (d.get("name") or "").upper().strip()
        isin = (d.get("isin") or "").upper().strip()

        if raw_ts:
            lookup[raw_ts] = key
            lookup[raw_ts.replace(" ", "")] = key
            lookup[raw_ts.replace("-", "")] = key
            lookup[raw_ts.replace(" ", "").replace("-", "")] = key
        if name:
            lookup[name] = key
            lookup[name.replace(" ", "")] = key
        if isin:
            lookup[isin] = key

        if seg == "NSE_FO":
            underlying = (d.get("underlying_symbol") or d.get("asset_symbol") or "").upper().strip()
            inst_type = (d.get("instrument_type") or "").upper().strip()
            strike = d.get("strike_price")
            expiry_ms = d.get("expiry")

            if underlying and expiry_ms:
                # Upstox expiry is millisecond epoch in UTC. IST is UTC+5:30.
                exp_dt = dt.datetime.fromtimestamp(expiry_ms / 1000, tz=dt.UTC)
                exp_ist = exp_dt + dt.timedelta(hours=5, minutes=30)
                yy = exp_ist.strftime("%y")
                mon = MONTH_NAMES[exp_ist.month - 1]
                dd = exp_ist.strftime("%d")

                underlying_clean = underlying.replace("-", "")

                if inst_type in ("CE", "PE") and strike is not None:
                    strike_str = f"{strike:.2f}".rstrip("0").rstrip(".")

                    # 1. Standard Monthly NSE: ADANIPORTS26SEP1800CE
                    lookup[f"{underlying}{yy}{mon}{strike_str}{inst_type}"] = key
                    lookup[f"{underlying_clean}{yy}{mon}{strike_str}{inst_type}"] = key

                    # 2. Weekly with day: ADANIPORTS26SEP291800CE
                    lookup[f"{underlying}{yy}{mon}{dd}{strike_str}{inst_type}"] = key
                    lookup[f"{underlying_clean}{yy}{mon}{dd}{strike_str}{inst_type}"] = key

                    # 3. Weekly NSE single-char month format: NIFTY2692224000PE (1-9, O, N, D)
                    m_char = (
                        str(exp_ist.month)
                        if exp_ist.month < 10
                        else ("O" if exp_ist.month == 10 else ("N" if exp_ist.month == 11 else "D"))
                    )
                    lookup[f"{underlying}{yy}{m_char}{dd}{strike_str}{inst_type}"] = key
                    lookup[f"{underlying_clean}{yy}{m_char}{dd}{strike_str}{inst_type}"] = key

                elif inst_type == "FUT":
                    # Futures: ADANIPORTS26SEPFUT
                    lookup[f"{underlying}{yy}{mon}FUT"] = key
                    lookup[f"{underlying_clean}{yy}{mon}FUT"] = key
                    lookup[f"{underlying}{yy}{mon}{dd}FUT"] = key
                    lookup[f"{underlying_clean}{yy}{mon}{dd}FUT"] = key

    return lookup


def fetch_and_parse_upstox_instruments(url: Optional[str] = None) -> dict[str, str]:
    """Download Upstox compressed instrument master and build symbol lookup mapping.

    Args:
        url: Master file URL (defaults to ``UPSTOX_NSE_INSTRUMENTS_URL``).

    Returns:
        Dictionary mapping all symbol variants to Upstox ``instrument_key``.
    """
    target_url = url or UPSTOX_NSE_INSTRUMENTS_URL
    logger.info("Fetching Upstox instrument master from %s...", target_url)

    req = urllib.request.Request(
        target_url,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        with gzip.GzipFile(fileobj=resp) as gz:
            data = json.load(gz)

    logger.info("Fetched %d raw items from Upstox master feed. Building lookup...", len(data))
    lookup = build_upstox_lookup(data)
    logger.info("Constructed Upstox lookup map with %d entries.", len(lookup))
    return lookup


def sync_upstox_instruments_to_redis(
    redis_client: Any,
    ttl_seconds: int = 172800,  # 48 hours
    chunk_size: int = 10000,
) -> int:
    """Download Upstox master file and cache all instrument keys in Redis.

    Args:
        redis_client: Connected Redis client.
        ttl_seconds: Redis hash TTL in seconds (default 48 hours).
        chunk_size: Pipelining batch size.

    Returns:
        Total number of keys written to Redis.
    """
    if redis_client is None:
        logger.warning("No Redis client provided. Skipping Upstox instrument sync to Redis.")
        return 0

    try:
        lookup = fetch_and_parse_upstox_instruments()
        if not lookup:
            logger.warning("Empty Upstox instrument lookup. Aborting Redis sync.")
            return 0

        # Update in-memory cache as well
        _IN_MEMORY_KEY_CACHE.update(lookup)

        # Write to Redis Hash in chunks
        items = list(lookup.items())
        total = len(items)

        for i in range(0, total, chunk_size):
            chunk = dict(items[i : i + chunk_size])
            redis_client.hset(REDIS_KEY_UPSTOX_INSTRUMENTS, mapping=chunk)

        redis_client.expire(REDIS_KEY_UPSTOX_INSTRUMENTS, ttl_seconds)
        logger.info(
            "Successfully synced %d Upstox instrument keys into Redis hash %s.",
            total,
            REDIS_KEY_UPSTOX_INSTRUMENTS,
        )
        return total
    except Exception as exc:
        logger.exception("Failed to sync Upstox instruments to Redis: %s", exc)
        return 0


def resolve_upstox_instrument_key(
    symbol: str,
    redis_client: Optional[Any] = None,
    db: Optional[Session] = None,
    access_token: Optional[str] = None,
) -> Optional[str]:
    """Resolve a stock or derivative contract symbol to an Upstox instrument key.

    Resolution hierarchy:
    1. Already formatted key (``NSE_EQ|...``, ``NSE_FO|...``, ``NSE_INDEX|...``, etc.)
    2. In-memory cache
    3. Redis hash ``market:upstox:instruments``
    4. Database ``Instrument`` table (for equities ISIN / index)
    5. Automatic cold-cache sync to Redis from master feed if Redis hash is empty
    6. Upstox Search API (``GET /v2/instruments/search``) if token available
    7. Fallback guard: if contract is a derivative (Option / Future) and still
       unresolved, returns ``None`` to prevent circuit breaker trip.

    Args:
        symbol: Symbol or contract string (e.g. 'ADANIPORTS26SEP1800CE', 'RELIANCE', 'NIFTY 50').
        redis_client: Optional Redis client.
        db: Optional SQLAlchemy Session.
        access_token: Optional Upstox Bearer token for search API fallback.

    Returns:
        Valid Upstox instrument_key string or None if unresolvable.
    """
    if not symbol:
        return None

    raw = symbol.strip()

    # 1. Already formatted key with pipe separator
    if "|" in raw:
        prefix, token = raw.split("|", 1)
        token_clean = token.upper().replace("-EQ", "").strip()
        # If token is a valid 12-char Indian ISIN
        if token_clean.startswith(("INE", "INF", "IN9")) and len(token_clean) == 12:
            key = f"{prefix}|{token_clean}"
            _IN_MEMORY_KEY_CACHE[symbol] = key
            return key
        if prefix in ("NSE_INDEX", "BSE_INDEX", "NSE_FO"):
            _IN_MEMORY_KEY_CACHE[symbol] = raw
            return raw
        clean_symbol = token_clean
    else:
        clean_symbol = raw.upper().replace("-EQ", "").strip()

    # If the clean symbol itself is an ISIN
    if clean_symbol.startswith(("INE", "INF", "IN9")) and len(clean_symbol) == 12:
        key = f"NSE_EQ|{clean_symbol}"
        _IN_MEMORY_KEY_CACHE[symbol] = key
        return key

    # 2. Check in-memory cache
    if clean_symbol in _IN_MEMORY_KEY_CACHE:
        return _IN_MEMORY_KEY_CACHE[clean_symbol]

    # 3. Check Redis hash
    if redis_client is not None:
        try:
            val = redis_client.hget(REDIS_KEY_UPSTOX_INSTRUMENTS, clean_symbol)
            if not val:
                val = redis_client.hget(REDIS_KEY_UPSTOX_INSTRUMENTS, clean_symbol.replace("-", ""))
            if not val:
                val = redis_client.hget(REDIS_KEY_UPSTOX_INSTRUMENTS, clean_symbol.replace(" ", ""))

            if val:
                decoded = val.decode("utf-8") if isinstance(val, bytes) else str(val)
                _IN_MEMORY_KEY_CACHE[symbol] = decoded
                _IN_MEMORY_KEY_CACHE[clean_symbol] = decoded
                return decoded
        except Exception as exc:
            logger.warning("Redis lookup failed for Upstox instrument %s: %s", clean_symbol, exc)

    # 4. Check DB Instrument table (for plain equities and indices)
    if db is not None:
        try:
            row = (
                db.query(Instrument.isin, Instrument.is_index)
                .filter(func.upper(Instrument.symbol) == clean_symbol)
                .first()
            )
            if row:
                if row.is_index == 1:
                    key = f"NSE_INDEX|{clean_symbol}"
                elif row.isin:
                    key = f"NSE_EQ|{row.isin}"
                else:
                    key = f"NSE_EQ|{clean_symbol}"
                _IN_MEMORY_KEY_CACHE[symbol] = key
                _IN_MEMORY_KEY_CACHE[clean_symbol] = key
                return key
        except Exception as exc:
            logger.warning("DB lookup failed for Upstox instrument %s: %s", clean_symbol, exc)

    # Detect if symbol is a derivative contract
    is_derivative = False
    try:
        parsed = parse_trading_symbol(clean_symbol)
        if parsed.instrument_type in (
            InstrumentTypeEnum.CE,
            InstrumentTypeEnum.PE,
            InstrumentTypeEnum.FUT,
        ):
            is_derivative = True
    except Exception:
        if any(clean_symbol.endswith(suffix) for suffix in ("CE", "PE", "FUT")):
            is_derivative = True

    # 5. Cold cache: if Redis hash is empty, populate from master feed on the fly
    if redis_client is not None:
        try:
            count = redis_client.hlen(REDIS_KEY_UPSTOX_INSTRUMENTS)
            if count == 0:
                logger.info("Redis Upstox instruments hash is empty. Priming from master feed...")
                sync_upstox_instruments_to_redis(redis_client)
                val = redis_client.hget(REDIS_KEY_UPSTOX_INSTRUMENTS, clean_symbol)
                if not val:
                    val = redis_client.hget(
                        REDIS_KEY_UPSTOX_INSTRUMENTS, clean_symbol.replace("-", "")
                    )
                if val:
                    decoded = val.decode("utf-8") if isinstance(val, bytes) else str(val)
                    _IN_MEMORY_KEY_CACHE[symbol] = decoded
                    _IN_MEMORY_KEY_CACHE[clean_symbol] = decoded
                    return decoded
        except Exception as exc:
            logger.warning("Auto-priming Redis Upstox instruments failed: %s", exc)

    # 6. Upstox Search API fallback if access token available
    if access_token:
        try:
            search_url = UpstoxApiConfig.url("/instruments/search")
            headers = UpstoxApiConfig.bearer_headers(access_token)
            params = {"query": clean_symbol}
            if is_derivative:
                params["segments"] = "FO"
            resp = requests.get(search_url, headers=headers, params=params, timeout=10)
            if resp.ok:
                resp_json = resp.json()
                items = resp_json.get("data", [])
                if items:
                    for item in items:
                        item_ts = (item.get("trading_symbol") or "").upper().replace(" ", "")
                        item_key = item.get("instrument_key")
                        if item_key:
                            if item_ts == clean_symbol.replace(
                                " ", ""
                            ) or item_ts == clean_symbol.replace("-", ""):
                                _IN_MEMORY_KEY_CACHE[symbol] = item_key
                                _IN_MEMORY_KEY_CACHE[clean_symbol] = item_key
                                if redis_client is not None:
                                    try:
                                        redis_client.hset(
                                            REDIS_KEY_UPSTOX_INSTRUMENTS, clean_symbol, item_key
                                        )
                                    except Exception:
                                        pass
                                return item_key
                    # Fallback to first item if segment matches
                    first_key = items[0].get("instrument_key")
                    if first_key:
                        _IN_MEMORY_KEY_CACHE[symbol] = first_key
                        return first_key
        except Exception as exc:
            logger.warning("Upstox Search API failed for %s: %s", clean_symbol, exc)

    # 7. Derivative safety guard: NEVER send NSE_EQ for an option or future!
    if is_derivative:
        logger.error(
            "Could not resolve Upstox instrument key for derivative contract %s. Rejecting to prevent circuit breaker trip.",
            clean_symbol,
        )
        return None

    # Plain equity fallback
    logger.warning("Unresolved equity instrument %s. Returning None.", clean_symbol)
    return None


def reset_upstox_circuit_breaker(redis_client: Any, endpoint_class: str = "order") -> bool:
    """Reset the Upstox circuit breaker to CLOSED in Redis.

    Args:
        redis_client: Connected Redis client.
        endpoint_class: Circuit breaker endpoint class (default 'order').

    Returns:
        True if breaker was successfully reset.
    """
    if redis_client is None:
        return False
    try:
        key = f"http:breaker:UPSTOX:{endpoint_class}"
        redis_client.hset(key, mapping={"state": 1, "failures": 0})
        logger.info("Successfully reset Upstox circuit breaker for %s to CLOSED in Redis.", key)
        return True
    except Exception as exc:
        logger.exception("Failed to reset Upstox circuit breaker in Redis: %s", exc)
        return False
