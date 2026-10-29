"""Angel One instrument master cache and symbol resolution.

Maintains a mapping of NSE equities and F&O derivative contracts from Angel
One's public scrip master feed
(``https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json``).

Angel One's SmartAPI requires three fields together to identify a contract —
``exchange``, ``tradingsymbol`` and ``symboltoken`` — unlike Upstox's single
composite instrument key, so resolution here returns an ``AngelOneContract``
rather than a string.
"""

import datetime as dt
import json
import logging
import time
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from tb_utils.models.instrument import Instrument
from tb_utils.options.contracts import parse_option_contract_symbol

logger = logging.getLogger(__name__)

ANGELONE_SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)
REDIS_KEY_ANGELONE_INSTRUMENTS = "market:angelone:instruments"
# Options, keyed by (underlying, expiry, strike, type) rather than by Angel's own spelling.
REDIS_KEY_ANGELONE_OPTIONS = "market:angelone:options"
DEFAULT_EXCHANGES = ("NSE", "NFO")
OPTION_INSTRUMENT_TYPES = ("OPTSTK", "OPTIDX")
# How long a worker trusts its in-memory option index before it asks Redis again, so a series listed
# after the worker started is eventually seen.
OPTION_INDEX_TTL_SECONDS = 12 * 3600

# pylint: disable=global-statement  # the option index is a deliberate module-level cache with a clock
_IN_MEMORY_CONTRACT_CACHE: dict[str, "AngelOneContract"] = {}
_OPTION_INDEX: dict[str, "AngelOneContract"] = {}
_option_index_loaded_at: Optional[float] = None
_monotonic = time.monotonic  # a seam so tests can move the clock


@dataclass(frozen=True)
class AngelOneContract:
    """The three fields Angel One's order/quote APIs require together, plus the contract's limits.

    ``lot_size``, ``tick_size`` and ``freeze_qty`` come from the scrip master. They default to 0
    ("unknown") so a contract cached before they existed still loads, and callers must treat 0 as
    "not known", never as a real limit.
    """

    exchange: str
    tradingsymbol: str
    symboltoken: str
    lot_size: int = 0
    tick_size: float = 0.0  # rupees; the master stores it times 100
    freeze_qty: int = 0  # largest quantity one order may carry


def contract_from_row(item: dict[str, Any]) -> AngelOneContract:
    """One scrip-master row as a contract."""
    return AngelOneContract(
        exchange=str(item.get("exch_seg") or "").upper(),
        tradingsymbol=str(item.get("symbol") or "").upper().strip(),
        symboltoken=str(item.get("token") or "").strip(),
        lot_size=int(float(item.get("lotsize") or 0)),
        tick_size=round(float(item.get("tick_size") or 0) / 100.0, 4),
        freeze_qty=int(float(item.get("freeze_qty") or 0)),
    )


def _strike_text(strike: float) -> str:
    return f"{strike:.2f}".rstrip("0").rstrip(".")


def option_index_key(name: str, expiry: dt.date, strike: float, option_type: str) -> str:
    """``TATASTEEL|2026-11-23|150|PE``: how an option is found, whatever either side calls it."""
    return f"{name.strip().upper()}|{expiry.isoformat()}|{_strike_text(strike)}|{option_type}"


def _option_row_key(item: dict[str, Any]) -> Optional[str]:
    """The index key for an option row, or None for anything that is not a listed option."""
    if str(item.get("exch_seg") or "").upper() != "NFO":
        return None
    if item.get("instrumenttype") not in OPTION_INSTRUMENT_TYPES:
        return None
    symbol = str(item.get("symbol") or "").upper().strip()
    if symbol[-2:] not in ("CE", "PE"):
        return None
    try:
        expiry = dt.datetime.strptime(str(item.get("expiry") or ""), "%d%b%Y").date()
        strike = float(item.get("strike")) / 100.0  # the master stores it times 100
    except (TypeError, ValueError):
        return None
    name = str(item.get("name") or "").upper().strip()
    if not name or strike <= 0 or not item.get("token"):
        return None
    return option_index_key(name, expiry, strike, symbol[-2:])


def build_angelone_option_index(items: list[dict[str, Any]]) -> dict[str, AngelOneContract]:
    """Every listed option, keyed by :func:`option_index_key`. Futures and equities are left out."""
    index: dict[str, AngelOneContract] = {}
    for item in items:
        key = _option_row_key(item)
        if key is not None:
            index[key] = contract_from_row(item)
    return index


def load_option_index(index: dict[str, AngelOneContract]) -> None:
    """Replace the in-memory option index (and start its clock)."""
    global _option_index_loaded_at
    _OPTION_INDEX.clear()
    _OPTION_INDEX.update(index)
    _option_index_loaded_at = _monotonic()


def clear_option_index() -> None:
    global _option_index_loaded_at
    _OPTION_INDEX.clear()
    _option_index_loaded_at = None


def option_index_size() -> int:
    return len(_OPTION_INDEX)


def option_index_expired() -> bool:
    """True once the index has been held longer than ``OPTION_INDEX_TTL_SECONDS``."""
    return (
        _option_index_loaded_at is not None
        and _monotonic() - _option_index_loaded_at > OPTION_INDEX_TTL_SECONDS
    )


def fetch_angelone_scrip_master(url: Optional[str] = None) -> list[dict[str, Any]]:
    """Download and parse Angel One's public scrip master JSON."""
    target_url = url or ANGELONE_SCRIP_MASTER_URL
    logger.info("Fetching Angel One scrip master from %s...", target_url)
    req = urllib.request.Request(target_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    logger.info("Fetched %d raw items from Angel One scrip master.", len(data))
    return data


def build_angelone_lookup(
    items: list[dict[str, Any]], exchanges: tuple[str, ...] = DEFAULT_EXCHANGES
) -> dict[str, AngelOneContract]:
    """Build a symbol → ``AngelOneContract`` map for the given exchange segments.

    Angel One's scrip master lists one row per contract (including each option
    and futures expiry), keyed by its own ``token`` — this covers equities and
    F&O contracts alike via the same generic pass.
    """
    lookup: dict[str, AngelOneContract] = {}
    for d in items:
        exch = str(d.get("exch_seg") or "").upper()
        if exch not in exchanges:
            continue
        symbol = str(d.get("symbol") or "").upper().strip()
        token = str(d.get("token") or "").strip()
        name = str(d.get("name") or "").upper().strip()
        if not symbol or not token:
            continue

        contract = contract_from_row(d)
        lookup[symbol] = contract
        if symbol.endswith("-EQ"):
            lookup.setdefault(symbol[: -len("-EQ")], contract)
        if name:
            lookup.setdefault(name, contract)

    return lookup


def sync_angelone_instruments_to_redis(
    redis_client: Any, ttl_seconds: int = 172800, chunk_size: int = 5000
) -> int:
    """Download the scrip master and cache all resolved contracts in Redis."""
    if redis_client is None:
        logger.warning("No Redis client provided. Skipping Angel One instrument sync to Redis.")
        return 0

    try:
        items = fetch_angelone_scrip_master()
        lookup = build_angelone_lookup(items)
        if not lookup:
            logger.warning("Empty Angel One instrument lookup. Aborting Redis sync.")
            return 0

        _IN_MEMORY_CONTRACT_CACHE.update(lookup)
        options = build_angelone_option_index(items)
        load_option_index(options)
        option_pairs = [(key, json.dumps(asdict(c))) for key, c in options.items()]
        for i in range(0, len(option_pairs), chunk_size):
            chunk = dict(option_pairs[i : i + chunk_size])
            redis_client.hset(REDIS_KEY_ANGELONE_OPTIONS, mapping=chunk)
        redis_client.expire(REDIS_KEY_ANGELONE_OPTIONS, ttl_seconds)

        pairs = [(sym, json.dumps(asdict(contract))) for sym, contract in lookup.items()]
        for i in range(0, len(pairs), chunk_size):
            chunk = dict(pairs[i : i + chunk_size])
            redis_client.hset(REDIS_KEY_ANGELONE_INSTRUMENTS, mapping=chunk)
        redis_client.expire(REDIS_KEY_ANGELONE_INSTRUMENTS, ttl_seconds)

        logger.info(
            "Successfully synced %d Angel One instrument keys into Redis hash %s.",
            len(pairs),
            REDIS_KEY_ANGELONE_INSTRUMENTS,
        )
        return len(pairs)
    except Exception:
        logger.exception("Failed to sync Angel One instruments to Redis")
        return 0


def _lookup_redis(clean: str, redis_client: Optional[Any]) -> Optional[AngelOneContract]:
    if redis_client is None:
        return None
    try:
        val = redis_client.hget(REDIS_KEY_ANGELONE_INSTRUMENTS, clean) or redis_client.hget(
            REDIS_KEY_ANGELONE_INSTRUMENTS, f"{clean}-EQ"
        )
        if not val:
            return None
        decoded = val.decode("utf-8") if isinstance(val, bytes) else str(val)
        return AngelOneContract(**json.loads(decoded))
    except Exception:
        logger.warning("Redis lookup failed for Angel One instrument %s", clean)
        return None


def _lookup_db(clean: str, db: Optional[Session]) -> Optional[AngelOneContract]:
    """Equity/index fallback via ``Instrument.angelone_token`` — F&O isn't in this table."""
    if db is None:
        return None
    try:
        row = (
            db.query(Instrument.angelone_token, Instrument.symbol)
            .filter(func.upper(Instrument.symbol) == clean.replace("-EQ", ""))
            .first()
        )
        if row and row.angelone_token:
            return AngelOneContract(
                exchange="NSE",
                tradingsymbol=f"{row.symbol.upper()}-EQ",
                symboltoken=row.angelone_token,
            )
    except Exception:
        logger.warning("DB lookup failed for Angel One instrument %s", clean)
    return None


def _resolve_option(clean: str, redis_client: Optional[Any]) -> Optional[AngelOneContract]:
    """An option given in our compact spelling (``UNDERLYING+YY+MON+DD+STRIKE+TYPE``), or None.

    Looked up by (underlying, expiry, strike, type), never by string, because Angel orders the date
    differently. Memory first, then one Redis field; an empty Redis is primed once from the master.
    """
    global _option_index_loaded_at
    parts = parse_option_contract_symbol(clean)
    if parts is None:
        return None
    if option_index_expired():
        clear_option_index()  # entries come back lazily from Redis, so a new series is picked up
    key = option_index_key(parts.underlying, parts.expiry, parts.strike, parts.option_type)
    if key in _OPTION_INDEX:
        return _OPTION_INDEX[key]
    if redis_client is None:
        return None
    contract = _lookup_option_redis(key, redis_client)
    if contract is None:
        try:
            if redis_client.hlen(REDIS_KEY_ANGELONE_OPTIONS) == 0:
                logger.info("Redis Angel One option hash is empty. Priming from scrip master...")
                sync_angelone_instruments_to_redis(redis_client)
                contract = _OPTION_INDEX.get(key)
        except Exception:
            logger.warning("Auto-priming Redis Angel One option index failed")
    if contract is not None:
        _OPTION_INDEX[key] = contract
        if _option_index_loaded_at is None:
            _option_index_loaded_at = _monotonic()
    return contract


def _lookup_option_redis(key: str, redis_client: Any) -> Optional[AngelOneContract]:
    try:
        val = redis_client.hget(REDIS_KEY_ANGELONE_OPTIONS, key)
        if not val:
            return None
        decoded = val.decode("utf-8") if isinstance(val, bytes) else str(val)
        return AngelOneContract(**json.loads(decoded))
    except Exception:
        logger.warning("Redis lookup failed for Angel One option %s", key)
        return None


def resolve_angelone_contract(
    symbol: str, redis_client: Optional[Any] = None, db: Optional[Session] = None
) -> Optional[AngelOneContract]:
    """Resolve a stock or derivative contract symbol to an ``AngelOneContract``.

    Resolution order: an option in our compact spelling, by (underlying, expiry,
    strike, type) → in-memory cache → Redis hash (cold-priming it from the
    scrip master if empty) → DB ``Instrument.angelone_token`` (equities/indices
    only). Returns ``None`` rather than guessing when a derivative contract
    can't be resolved, to avoid sending a malformed order.
    """
    if not symbol:
        return None

    clean = symbol.upper().strip().replace(" ", "")

    # Our compact option spelling first: it is what the order engine sends. Angel's own spelling
    # (``TATASTEEL23NOV26150PE``) reads as a compact symbol for a past date, which is not listed,
    # so it falls through to the exact-symbol lookup below.
    option = _resolve_option(clean, redis_client)
    if option is not None:
        return option

    if clean in _IN_MEMORY_CONTRACT_CACHE:
        return _IN_MEMORY_CONTRACT_CACHE[clean]

    contract = _lookup_redis(clean, redis_client)

    if contract is None and redis_client is not None:
        try:
            if redis_client.hlen(REDIS_KEY_ANGELONE_INSTRUMENTS) == 0:
                logger.info(
                    "Redis Angel One instruments hash is empty. Priming from scrip master..."
                )
                sync_angelone_instruments_to_redis(redis_client)
                contract = _lookup_redis(clean, redis_client)
        except Exception:
            logger.warning("Auto-priming Redis Angel One instruments failed")

    if contract is None:
        contract = _lookup_db(clean, db)

    if contract is not None:
        _IN_MEMORY_CONTRACT_CACHE[clean] = contract
        return contract

    logger.error("Could not resolve Angel One contract for symbol %s", clean)
    return None
