"""ICICI Direct (Breeze) instrument master cache and symbol resolution.

Breeze identifies a contract by ICICI's own ``stock_code`` (``RELIND`` for
RELIANCE, ``CNXBAN`` for BANKNIFTY) plus, for derivatives, an expiry, a strike
and a right, rather than by a single token the way Upstox does. The mapping
comes from ICICI's public security master
(``https://directlink.icicidirect.com/MotherAppMaster/SecurityMaster.zip``),
which holds one pipe-free CSV per segment. Only two are used here:

* ``NSEScripMaster.txt``: cash equities. ``ShortName`` is the Breeze
  ``stock_code``; the last column, ``ExchangeCode``, is the NSE symbol.
* ``FONSEScripMaster.txt``: NFO futures and options. ``ShortName`` is the
  Breeze ``stock_code`` of the underlying; the last column is the NSE
  underlying name (``RELIANCE``, ``NIFTY 50``, ``NIFTY BANK``).

Callers hand in the symbol shapes the rest of the platform uses, not ICICI's:
``RELIANCE`` for cash, ``ADANIPORTS26SEP1800CE`` / ``NIFTY27OCT2625000CE`` /
``TATASTEEL 29OCT 185 CE`` for options and ``RELIANCE26OCTFUT`` for futures.
"""

import csv
import datetime as dt
import io
import json
import logging
import re
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from tb_utils.models.instrument import Instrument

logger = logging.getLogger(__name__)

ICICI_SECURITY_MASTER_URL = "https://directlink.icicidirect.com/MotherAppMaster/SecurityMaster.zip"
REDIS_KEY_ICICI_INSTRUMENTS = "market:icici:instruments"
REDIS_KEY_ICICI_EXPIRIES = "market:icici:expiries"
REDIS_KEY_ICICI_CODES = "market:icici:codes"  # ICICI stock_code -> platform symbol

CASH_FILE = "NSEScripMaster.txt"
FNO_FILE = "FONSEScripMaster.txt"

# Cash series ranked so the main-board "EQ" row wins when a symbol is listed in several.
_CASH_SERIES_PRIORITY = {"EQ": 3, "BE": 2, "SM": 1, "ST": 1}

# Index underlyings: platform name -> (Breeze stock_code, name in the F&O master's last column).
INDEX_UNDERLYINGS: dict[str, tuple[str, str]] = {
    "NIFTY50": ("NIFTY", "NIFTY 50"),
    "BANKNIFTY": ("CNXBAN", "NIFTY BANK"),
    "FINNIFTY": ("NIFFIN", "NIFTY FINANCIAL"),
    "MIDCPNIFTY": ("NIFSEL", "NIFTY MIDCAP"),
    "NIFTYNXT50": ("NIFNEX", "NIFTY NEXT 50"),
}
_INDEX_ALIASES: dict[str, str] = {
    "NIFTY": "NIFTY50",
    "NIFTY 50": "NIFTY50",
    "NIFTY BANK": "BANKNIFTY",
    "NIFTYBANK": "BANKNIFTY",
    "NIFTY FINANCIAL": "FINNIFTY",
    "NIFTYFINANCIAL": "FINNIFTY",
    "NIFTY MIDCAP": "MIDCPNIFTY",
    "NIFTY NEXT 50": "NIFTYNXT50",
    "NIFTYNEXT50": "NIFTYNXT50",
}
_INDEX_BY_MASTER_NAME = {name: platform for platform, (_, name) in INDEX_UNDERLYINGS.items()}

_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_MON_RE = "|".join(_MONTHS)
# NSE weekly month codes: 1-9 for Jan-Sep, then O, N, D.
_WEEKLY_MONTH = {**{str(i): i for i in range(1, 10)}, "O": 10, "N": 11, "D": 12}

_IN_MEMORY_CONTRACT_CACHE: dict[str, "ICICIContract"] = {}


@dataclass(frozen=True)
class ICICIContract:
    """What Breeze's order and quote calls need to identify an instrument."""

    exchange_code: str  # "NSE" (cash) or "NFO" (futures and options)
    stock_code: str  # ICICI short name, e.g. RELIND, NIFTY, CNXBAN
    product_type: str  # "cash", "futures" or "options"
    expiry_date: str = ""  # ISO date; "" for cash
    right: str = ""  # "call", "put" or ""
    strike_price: str = ""  # whole or decimal rupees; "" for cash and futures
    lot_size: int = 1
    token: str = ""
    tick_size: float = 0.05  # rupees; orders must be priced on a multiple of it

    @property
    def breeze_expiry(self) -> str:
        """Expiry as Breeze expects it: ISO date at 06:00 UTC, or "" for cash."""
        return f"{self.expiry_date}T06:00:00.000Z" if self.expiry_date else ""


# ── Download and parse ──────────────────────────────────────────────────────


def fetch_icici_security_master(url: Optional[str] = None) -> dict[str, list[dict[str, str]]]:
    """Download the security master zip and return the cash and F&O files as row dicts."""
    target = url or ICICI_SECURITY_MASTER_URL
    logger.info("Fetching ICICI security master from %s...", target)
    req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()

    files: dict[str, list[dict[str, str]]] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in (CASH_FILE, FNO_FILE):
            if name not in archive.namelist():
                logger.warning("ICICI security master has no %s", name)
                continue
            with archive.open(name) as handle:
                reader = csv.DictReader(
                    io.TextIOWrapper(handle, encoding="utf-8"), skipinitialspace=True
                )
                files[name] = [
                    {(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader
                ]
    logger.info("Fetched ICICI security master: %s", {k: len(v) for k, v in files.items()})
    return files


def _to_int(value: str, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value: str, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _fmt_strike(value: float) -> str:
    return f"{value:g}"


def _platform_underlying(master_name: str) -> str:
    """The platform's name for an F&O underlying: NSE symbol for stocks, our index names for indices."""
    name = master_name.strip().upper()
    return _INDEX_BY_MASTER_NAME.get(name, name)


def build_icici_cash_lookup(rows: list[dict[str, str]]) -> dict[str, ICICIContract]:
    """NSE symbol (and ICICI short name) -> cash ``ICICIContract``; index spots included."""
    best: dict[str, tuple[int, ICICIContract]] = {}
    for row in rows:
        nse_symbol = row.get("ExchangeCode", "").upper()
        short_name = row.get("ShortName", "").upper()
        series = row.get("Series", "").upper()
        rank = _CASH_SERIES_PRIORITY.get(series)
        if not nse_symbol or not short_name or rank is None:
            continue
        contract = ICICIContract(
            exchange_code="NSE",
            stock_code=short_name,
            product_type="cash",
            lot_size=_to_int(row.get("Lotsize", "1")),
            token=row.get("Token", ""),
            tick_size=_to_float(row.get("ticksize", ""), 0.05),
        )
        if nse_symbol not in best or rank > best[nse_symbol][0]:
            best[nse_symbol] = (rank, contract)

    lookup = {sym: contract for sym, (_, contract) in best.items()}
    for contract in list(lookup.values()):
        lookup.setdefault(contract.stock_code, contract)

    # Index spots are not in the cash file; Breeze quotes them as NSE cash under the index code.
    for platform, (code, master_name) in INDEX_UNDERLYINGS.items():
        spot = ICICIContract(exchange_code="NSE", stock_code=code, product_type="cash")
        for key in (platform, master_name, master_name.replace(" ", "")):
            lookup.setdefault(key, spot)
    return lookup


def build_icici_derivative_lookup(
    rows: list[dict[str, str]],
) -> tuple[dict[str, ICICIContract], dict[str, list[str]]]:
    """Derivative contracts keyed ``UND|expiry|strike|CE`` / ``UND|expiry|FUT``, plus each underlying's expiries."""
    contracts: dict[str, ICICIContract] = {}
    expiries: dict[str, set[str]] = {}
    for row in rows:
        instrument = row.get("InstrumentName", "").upper()
        if not instrument.startswith(("FUT", "OPT")):
            continue
        underlying = _platform_underlying(row.get("ExchangeCode", ""))
        short_name = row.get("ShortName", "").upper()
        try:
            expiry = dt.datetime.strptime(row.get("ExpiryDate", ""), "%d-%b-%Y").date().isoformat()
        except ValueError:
            continue
        if not underlying or not short_name:
            continue

        lot = _to_int(row.get("LotSize", "1"))
        tick = _to_float(row.get("TickSize", ""), 5.0) / 100  # the F&O file quotes paise
        if instrument.startswith("FUT"):
            key = f"{underlying}|{expiry}|FUT"
            contract = ICICIContract(
                exchange_code="NFO",
                stock_code=short_name,
                product_type="futures",
                expiry_date=expiry,
                lot_size=lot,
                token=row.get("Token", ""),
                tick_size=tick,
            )
        else:
            option_type = row.get("OptionType", "").upper()
            if option_type not in ("CE", "PE"):
                continue
            try:
                strike = float(row.get("StrikePrice", ""))
            except ValueError:
                continue
            strike_text = _fmt_strike(strike)
            key = f"{underlying}|{expiry}|{strike_text}|{option_type}"
            contract = ICICIContract(
                exchange_code="NFO",
                stock_code=short_name,
                product_type="options",
                expiry_date=expiry,
                right="call" if option_type == "CE" else "put",
                strike_price=strike_text,
                lot_size=lot,
                token=row.get("Token", ""),
                tick_size=tick,
            )
        contracts[key] = contract
        expiries.setdefault(underlying, set()).add(expiry)

    return contracts, {u: sorted(e) for u, e in expiries.items()}


def reverse_code_map(cash: dict[str, ICICIContract]) -> dict[str, str]:
    """ICICI ``stock_code`` -> the platform symbol (NSE symbol, or our index name), for positions and holdings."""
    codes: dict[str, str] = {}
    for platform, (code, _) in INDEX_UNDERLYINGS.items():
        codes[code] = platform
    for symbol, contract in cash.items():
        if contract.stock_code == symbol or contract.stock_code in codes:
            continue
        codes[contract.stock_code] = symbol
    return codes


def platform_symbol_for(
    stock_code: str,
    redis_client: Optional[Any],
    expiry: Optional[dt.date] = None,
    strike: Optional[float] = None,
    right: Optional[str] = None,
    product_type: str = "cash",
) -> str:
    """The platform symbol for something Breeze reports back (a position or a holding).

    Cash returns the NSE symbol. A future reads ``RELIANCE27OCT26FUT`` and an option
    ``RELIANCE27OCT261400CE``, the day-month-year form that ``resolve_icici_contract``
    reads back unambiguously. An unknown code is returned as is.
    """
    code = stock_code.strip().upper()
    underlying = code
    if redis_client is not None:
        try:
            val = redis_client.hget(REDIS_KEY_ICICI_CODES, code)
            if val:
                underlying = _decode(val)
        except Exception:
            logger.warning("Redis reverse lookup failed for ICICI code %s", code)
    if product_type == "cash" or expiry is None:
        return underlying

    stamp = f"{expiry.day:02d}{_MONTHS[expiry.month - 1]}{expiry.year % 100:02d}"
    if product_type == "futures":
        return f"{underlying}{stamp}FUT"
    kind = "CE" if (right or "").lower().startswith(("c", "ce")) else "PE"
    return f"{underlying}{stamp}{_fmt_strike(strike or 0)}{kind}"


# ── Redis sync ──────────────────────────────────────────────────────────────


def sync_icici_instruments_to_redis(
    redis_client: Any,
    ttl_seconds: int = 172800,
    chunk_size: int = 5000,
    files: Optional[dict[str, list[dict[str, str]]]] = None,
) -> int:
    """Cache cash, derivative, expiry and reverse-code maps in Redis.

    Downloads the security master unless the caller already has it (``files``).
    """
    if redis_client is None:
        logger.warning("No Redis client provided. Skipping ICICI instrument sync to Redis.")
        return 0

    try:
        files = files if files is not None else fetch_icici_security_master()
        if not files.get(CASH_FILE):
            # Index spots are always added to the lookup, so an empty download must be caught here.
            logger.warning("ICICI security master has no cash rows. Aborting Redis sync.")
            return 0
        cash = build_icici_cash_lookup(files[CASH_FILE])
        derivatives, expiries = build_icici_derivative_lookup(files.get(FNO_FILE, []))

        _IN_MEMORY_CONTRACT_CACHE.update(cash)

        pairs = [(k, json.dumps(asdict(c))) for k, c in {**cash, **derivatives}.items()]
        for i in range(0, len(pairs), chunk_size):
            redis_client.hset(REDIS_KEY_ICICI_INSTRUMENTS, mapping=dict(pairs[i : i + chunk_size]))
        redis_client.expire(REDIS_KEY_ICICI_INSTRUMENTS, ttl_seconds)

        codes = reverse_code_map(cash)
        if codes:
            redis_client.hset(REDIS_KEY_ICICI_CODES, mapping=codes)
            redis_client.expire(REDIS_KEY_ICICI_CODES, ttl_seconds)

        if expiries:
            redis_client.hset(
                REDIS_KEY_ICICI_EXPIRIES, mapping={u: json.dumps(e) for u, e in expiries.items()}
            )
            redis_client.expire(REDIS_KEY_ICICI_EXPIRIES, ttl_seconds)

        logger.info(
            "Synced %d ICICI instrument keys (%d cash, %d derivative) into Redis hash %s.",
            len(pairs),
            len(cash),
            len(derivatives),
            REDIS_KEY_ICICI_INSTRUMENTS,
        )
        return len(pairs)
    except Exception:
        logger.exception("Failed to sync ICICI instruments to Redis")
        return 0


def _decode(val: Any) -> str:
    return val.decode("utf-8") if isinstance(val, bytes) else str(val)


def _lookup_redis(key: str, redis_client: Optional[Any]) -> Optional[ICICIContract]:
    if redis_client is None:
        return None
    try:
        val = redis_client.hget(REDIS_KEY_ICICI_INSTRUMENTS, key)
        return ICICIContract(**json.loads(_decode(val))) if val else None
    except Exception:
        logger.warning("Redis lookup failed for ICICI instrument %s", key)
        return None


def _expiries_for(underlying: str, redis_client: Optional[Any]) -> list[dt.date]:
    if redis_client is None:
        return []
    try:
        val = redis_client.hget(REDIS_KEY_ICICI_EXPIRIES, underlying)
        return [dt.date.fromisoformat(e) for e in json.loads(_decode(val))] if val else []
    except Exception:
        logger.warning("Redis expiry lookup failed for ICICI underlying %s", underlying)
        return []


# ── Derivative symbol parsing ───────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedDerivative:
    """One reading of a derivative symbol. The same text can read several ways, so callers try each."""

    underlying: str
    right: Optional[str]  # "CE", "PE", or None for a future
    strike: Optional[float]
    expiry: Optional[dt.date] = None  # exact date, when the symbol carries day, month and year
    year_month: Optional[tuple[int, int]] = None  # month only: the month's last expiry
    day_month: Optional[tuple[int, int]] = None  # no year: the nearest upcoming such date


def _year(two_digits: str) -> int:
    return 2000 + int(two_digits)


def _safe_date(year: int, month: int, day: int) -> Optional[dt.date]:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


_STRIKE = r"(?P<strike>\d+(?:\.\d+)?)"
_RIGHT = r"(?P<right>CE|PE)"
_UND = r"(?P<und>[A-Z0-9&\-]+?)"

_OPTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ymon", rf"^{_UND}(?P<yy>\d{{2}}){'(?P<mon>' + _MON_RE + ')'}{_STRIKE}{_RIGHT}$"),
    (
        "dmony",
        rf"^{_UND}(?P<dd>\d{{2}}){'(?P<mon>' + _MON_RE + ')'}(?P<yy>\d{{2}}){_STRIKE}{_RIGHT}$",
    ),
    ("dmon", rf"^{_UND}(?P<dd>\d{{1,2}}){'(?P<mon>' + _MON_RE + ')'}{_STRIKE}{_RIGHT}$"),
    ("weekly", rf"^{_UND}(?P<yy>\d{{2}})(?P<wm>[1-9OND])(?P<dd>\d{{2}}){_STRIKE}{_RIGHT}$"),
)
_FUTURE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ymon", rf"^{_UND}(?P<yy>\d{{2}}){'(?P<mon>' + _MON_RE + ')'}FUT$"),
    ("dmony", rf"^{_UND}(?P<dd>\d{{2}}){'(?P<mon>' + _MON_RE + ')'}(?P<yy>\d{{2}})FUT$"),
    ("dmon", rf"^{_UND}(?P<dd>\d{{1,2}}){'(?P<mon>' + _MON_RE + ')'}FUT$"),
)


def parse_derivative_symbol(symbol: str) -> list[ParsedDerivative]:
    """Every plausible reading of an option or future symbol, most likely first.

    ``ADANIPORTS26SEP1800CE`` reads as year 26 + SEP, but ``NIFTY27OCT2625000CE``
    reads as day 27 + OCT + year 26, and ``TATASTEEL29OCT185CE`` as day 29 + OCT with
    no year. The text alone cannot say which, so resolution checks each reading against
    the contracts that exist and keeps the one that does.
    """
    clean = re.sub(r"\s+", "", symbol.upper())
    readings: list[ParsedDerivative] = []

    for patterns, is_option in ((_OPTION_PATTERNS, True), (_FUTURE_PATTERNS, False)):
        for shape, pattern in patterns:
            m = re.match(pattern, clean)
            if not m:
                continue
            g = m.groupdict()
            und = g["und"]
            right = g.get("right")
            strike = float(g["strike"]) if is_option else None
            if shape == "ymon":
                readings.append(
                    ParsedDerivative(
                        und, right, strike, year_month=(_year(g["yy"]), _MONTHS.index(g["mon"]) + 1)
                    )
                )
            elif shape == "dmony":
                exp = _safe_date(_year(g["yy"]), _MONTHS.index(g["mon"]) + 1, int(g["dd"]))
                if exp:
                    readings.append(ParsedDerivative(und, right, strike, expiry=exp))
            elif shape == "dmon":
                readings.append(
                    ParsedDerivative(
                        und, right, strike, day_month=(_MONTHS.index(g["mon"]) + 1, int(g["dd"]))
                    )
                )
            elif shape == "weekly":
                exp = _safe_date(_year(g["yy"]), _WEEKLY_MONTH[g["wm"]], int(g["dd"]))
                if exp:
                    readings.append(ParsedDerivative(und, right, strike, expiry=exp))
    return readings


def _pick_expiry(
    reading: ParsedDerivative, expiries: list[dt.date], today: dt.date
) -> Optional[dt.date]:
    if reading.expiry:
        return reading.expiry if reading.expiry in expiries else None
    if reading.year_month:
        in_month = [e for e in expiries if (e.year, e.month) == reading.year_month]
        return max(in_month) if in_month else None
    if reading.day_month:
        month, day = reading.day_month
        upcoming = [e for e in expiries if e >= today and (e.month, e.day) == (month, day)]
        return min(upcoming) if upcoming else None
    return None


def _canonical_underlying(raw: str) -> str:
    name = raw.strip().upper()
    return _INDEX_ALIASES.get(name, _INDEX_ALIASES.get(name.replace(" ", ""), name))


def _resolve_derivative(
    clean: str, redis_client: Optional[Any], today: dt.date
) -> Optional[ICICIContract]:
    for reading in parse_derivative_symbol(clean):
        underlying = _canonical_underlying(reading.underlying)
        expiry = _pick_expiry(reading, _expiries_for(underlying, redis_client), today)
        if expiry is None:
            continue
        if reading.right is None:
            key = f"{underlying}|{expiry.isoformat()}|FUT"
        else:
            key = f"{underlying}|{expiry.isoformat()}|{_fmt_strike(reading.strike or 0)}|{reading.right}"
        contract = _lookup_redis(key, redis_client)
        if contract is not None:
            return contract
    return None


def _lookup_db(clean: str, db: Optional[Session]) -> Optional[ICICIContract]:
    """Equity fallback via ``Instrument.icici_stock_code``. Derivatives are not in that table."""
    if db is None:
        return None
    try:
        row = (
            db.query(Instrument.icici_stock_code)
            .filter(func.upper(Instrument.symbol) == clean)
            .first()
        )
        if row and row.icici_stock_code:
            return ICICIContract(
                exchange_code="NSE", stock_code=row.icici_stock_code, product_type="cash"
            )
    except Exception:
        logger.warning("DB lookup failed for ICICI instrument %s", clean)
    return None


def resolve_icici_contract(
    symbol: str,
    redis_client: Optional[Any] = None,
    db: Optional[Session] = None,
    today: Optional[dt.date] = None,
) -> Optional[ICICIContract]:
    """Resolve a platform symbol to the ``ICICIContract`` Breeze needs.

    Order: in-memory cache, then the Redis hashes (priming them from the security master
    if empty), then ``Instrument.icici_stock_code`` for equities. A derivative that cannot
    be matched to a listed contract returns ``None`` rather than a guess, so no malformed
    order reaches the broker.
    """
    if not symbol:
        return None

    clean = re.sub(r"\s+", "", symbol.upper().strip().replace("-EQ", ""))
    today = today or dt.date.today()
    if clean in _IN_MEMORY_CONTRACT_CACHE:
        return _IN_MEMORY_CONTRACT_CACHE[clean]

    def attempt() -> Optional[ICICIContract]:
        found = _lookup_redis(clean, redis_client)
        if found is None:
            found = _lookup_redis(_canonical_underlying(clean), redis_client)
        return found or _resolve_derivative(clean, redis_client, today)

    contract = attempt()
    if contract is None and redis_client is not None:
        try:
            if redis_client.hlen(REDIS_KEY_ICICI_INSTRUMENTS) == 0:
                logger.info(
                    "Redis ICICI instruments hash is empty. Priming from security master..."
                )
                sync_icici_instruments_to_redis(redis_client)
                contract = attempt()
        except Exception:
            logger.warning("Auto-priming Redis ICICI instruments failed")

    if contract is None:
        contract = _lookup_db(clean, db)

    if contract is not None:
        # Only cash resolutions are cached in memory: a derivative symbol embeds its expiry,
        # but a month-only or day-month symbol's meaning shifts as time passes.
        if contract.product_type == "cash":
            _IN_MEMORY_CONTRACT_CACHE[clean] = contract
        return contract

    logger.error("Could not resolve ICICI contract for symbol %s", clean)
    return None


def clear_icici_cache() -> None:
    """Forget in-memory resolutions. Used by tests and after a master re-sync."""
    _IN_MEMORY_CONTRACT_CACHE.clear()
