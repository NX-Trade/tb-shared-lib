"""Angel One instrument master cache and symbol resolution.

Maintains a mapping of NSE equities and F&O derivative contracts from Angel
One's public scrip master feed
(``https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json``).

Angel One's SmartAPI requires three fields together to identify a contract —
``exchange``, ``tradingsymbol`` and ``symboltoken`` — unlike Upstox's single
composite instrument key, so resolution here returns an ``AngelOneContract``
rather than a string.
"""

import json
import logging
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from tb_utils.models.instrument import Instrument

logger = logging.getLogger(__name__)

ANGELONE_SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)
REDIS_KEY_ANGELONE_INSTRUMENTS = "market:angelone:instruments"
DEFAULT_EXCHANGES = ("NSE", "NFO")

_IN_MEMORY_CONTRACT_CACHE: dict[str, "AngelOneContract"] = {}


@dataclass(frozen=True)
class AngelOneContract:
    """The three fields Angel One's order/quote APIs require together."""

    exchange: str
    tradingsymbol: str
    symboltoken: str


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

        contract = AngelOneContract(exchange=exch, tradingsymbol=symbol, symboltoken=token)
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


def resolve_angelone_contract(
    symbol: str, redis_client: Optional[Any] = None, db: Optional[Session] = None
) -> Optional[AngelOneContract]:
    """Resolve a stock or derivative contract symbol to an ``AngelOneContract``.

    Resolution order: in-memory cache → Redis hash (cold-priming it from the
    scrip master if empty) → DB ``Instrument.angelone_token`` (equities/indices
    only). Returns ``None`` rather than guessing when a derivative contract
    can't be resolved, to avoid sending a malformed order.
    """
    if not symbol:
        return None

    clean = symbol.upper().strip().replace(" ", "")
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
