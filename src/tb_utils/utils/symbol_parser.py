"""Parse broker trading symbols into structured derivative contract components.

Centralises the symbol classification logic that was previously scattered as
regexes in ``position_reconciler.py``. Every consumer (reconciler, fill booker,
UI) uses this single, tested entry point.

Examples::

    >>> parse_trading_symbol('RELIANCE')
    ParsedContract(underlying='RELIANCE', instrument_type=EQUITY, ...)

    >>> parse_trading_symbol('SONACOMS26SEP820CE')
    ParsedContract(underlying='SONACOMSTAR', instrument_type=CE, strike=820.0, ...)

    >>> parse_trading_symbol('NIFTY26SEPFUT')
    ParsedContract(underlying='NIFTY', instrument_type=FUT, ...)
"""

import calendar
import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from tb_utils.models import Instrument
from tb_utils.utils.common import get_instrument_map, resolve_instrument_id
from tb_utils.utils.enums import InstrumentTypeEnum

logger = logging.getLogger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────
# Option: SYMBOLYYMONSTRIKEPE/CE  e.g. SONACOMS26SEP820CE, NIFTY26SEP24000PE
# The underlying may be truncated by the exchange (SONACOMSTAR → SONACOMS).
_OPTION_RE = re.compile(
    r"^(?P<underlying>[A-Z0-9_&]+?)"  # underlying (greedy-reluctant)
    r"(?P<yy>\d{2})"  # 2-digit year
    r"(?P<mon>[A-Z]{3})"  # 3-letter month
    r"(?P<strike>\d+(?:\.\d+)?)"  # strike price
    r"(?P<opt_type>CE|PE)$",  # call or put
    re.IGNORECASE,
)

# Future: SYMBOLYYMONTHFUT  e.g. NIFTY26SEPFUT, RELIANCE26OCTFUT
_FUTURE_RE = re.compile(
    r"^(?P<underlying>[A-Z0-9_&]+?)"
    r"(?P<yy>\d{2})"
    r"(?P<mon>[A-Z]{3})"
    r"FUT$",
    re.IGNORECASE,
)

# Weekly Option: SYMBOLYYMDDSTRIKEPE/CE  e.g. NIFTY2692223400PE, BANKNIFTY26O0851000CE
# Month: 1-9 for Jan-Sep, O for Oct, N for Nov, D for Dec
_WEEKLY_OPTION_RE = re.compile(
    r"^(?P<underlying>[A-Z0-9_&]+?)"
    r"(?P<yy>\d{2})"
    r"(?P<m>[1-9OND])"
    r"(?P<dd>\d{2})"
    r"(?P<strike>\d+(?:\.\d+)?)"
    r"(?P<opt_type>CE|PE)$",
    re.IGNORECASE,
)

# Month abbreviation → month number
_MONTH_MAP = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}
_WEEKLY_MONTH_MAP = {
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "O": 10,
    "N": 11,
    "D": 12,
}


@dataclass(frozen=True)
class ParsedContract:
    """Structured breakdown of a broker trading symbol."""

    underlying_symbol: str
    instrument_type: InstrumentTypeEnum
    trading_symbol: str
    expiry_date: Optional[dt.date] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = (
        None  # 'CE' or 'PE' (redundant with instrument_type, kept for clarity)
    )


def _parse_expiry(yy: str, mon: str) -> Optional[dt.date]:
    """Parse '26' + 'SEP' into a date (last Thursday of the month as approximation)."""
    try:
        year = 2000 + int(yy)
        month = _MONTH_MAP.get(mon.upper())
        if month is None:
            return None
        # Use last day of month as a safe approximation; the exact expiry day
        # (last Thursday) requires an exchange calendar, which the reconciler
        # doesn't need for uniqueness — the full trading_symbol handles that.
        last_day = calendar.monthrange(year, month)[1]
        return dt.date(year, month, last_day)
    except (ValueError, KeyError):
        return None


def parse_trading_symbol(symbol: str) -> ParsedContract:
    """Parse a broker trading symbol into structured components.

    Returns a ``ParsedContract`` with the underlying symbol, instrument type,
    and derivative-specific fields (strike, expiry, option type) when applicable.

    Supports:
      - Monthly Options: ``SONACOMS26SEP820CE``, ``NIFTY26SEP24000PE``
      - Weekly Options: ``NIFTY2692223400PE``, ``BANKNIFTY26O0851000CE``
      - Futures: ``NIFTY26SEPFUT``, ``RELIANCE26OCTFUT``
      - Equities: ``RELIANCE``, ``SONACOMS``

    The underlying symbol extracted here may be a truncated exchange form
    (e.g. ``SONACOMS`` for ``SONACOMSTAR``) or index alias (``NIFTY`` for ``NIFTY50``).
    Use ``resolve_underlying_instrument_id`` to match against the instrument master.
    """
    cleaned = symbol.strip().upper()

    # 1. Try standard monthly option pattern
    m = _OPTION_RE.match(cleaned)
    if m:
        opt_type = m.group("opt_type").upper()
        return ParsedContract(
            underlying_symbol=m.group("underlying").upper(),
            instrument_type=InstrumentTypeEnum.CE if opt_type == "CE" else InstrumentTypeEnum.PE,
            trading_symbol=cleaned,
            expiry_date=_parse_expiry(m.group("yy"), m.group("mon")),
            strike_price=float(m.group("strike")),
            option_type=opt_type,
        )

    # 2. Try weekly option pattern (e.g. NIFTY2692223400PE)
    m = _WEEKLY_OPTION_RE.match(cleaned)
    if m:
        opt_type = m.group("opt_type").upper()
        year = 2000 + int(m.group("yy"))
        month = _WEEKLY_MONTH_MAP.get(m.group("m").upper(), 1)
        day = int(m.group("dd"))
        try:
            exp_date = dt.date(year, month, day)
        except ValueError:
            exp_date = None
        return ParsedContract(
            underlying_symbol=m.group("underlying").upper(),
            instrument_type=InstrumentTypeEnum.CE if opt_type == "CE" else InstrumentTypeEnum.PE,
            trading_symbol=cleaned,
            expiry_date=exp_date,
            strike_price=float(m.group("strike")),
            option_type=opt_type,
        )

    # 3. Try future pattern
    m = _FUTURE_RE.match(cleaned)
    if m:
        return ParsedContract(
            underlying_symbol=m.group("underlying").upper(),
            instrument_type=InstrumentTypeEnum.FUT,
            trading_symbol=cleaned,
            expiry_date=_parse_expiry(m.group("yy"), m.group("mon")),
        )

    # 4. Plain equity
    return ParsedContract(
        underlying_symbol=cleaned,
        instrument_type=InstrumentTypeEnum.EQUITY,
        trading_symbol=cleaned,
    )


def resolve_underlying_instrument_id(db: Session, underlying_symbol: str) -> Optional[int]:
    """Look up ``instrument_id`` for an underlying symbol.

    Handles broker symbol truncations (``SONACOMS`` → ``SONACOMSTAR``) and
    index aliases (``NIFTY`` → ``NIFTY50``) by trying exact match, alias map,
    and prefix match against ``instrument.symbol``.
    """

    # 1. Exact match
    row = db.query(Instrument.instrument_id).filter(Instrument.symbol == underlying_symbol).first()
    if row:
        return row.instrument_id

    # 2. Alias resolution (handles NIFTY -> NIFTY50, BANKNIFTY, FINNIFTY, IB symbols)
    try:
        inst_map = get_instrument_map(db)
        resolved = resolve_instrument_id(underlying_symbol, inst_map)
        if resolved is not None:
            return resolved
    except Exception as exc:
        logger.warning(
            "Failed to resolve alias for %s via get_instrument_map: %s", underlying_symbol, exc
        )

    # 3. Prefix match — the exchange truncates symbols like SONACOMSTAR → SONACOMS
    if len(underlying_symbol) >= 3:
        row = (
            db.query(Instrument.instrument_id)
            .filter(Instrument.symbol.startswith(underlying_symbol))
            .first()
        )
        if row:
            logger.info(
                "Symbol prefix match: %s resolved to instrument_id=%d",
                underlying_symbol,
                row.instrument_id,
            )
            return row.instrument_id

    logger.warning("Could not resolve underlying symbol %s to any instrument", underlying_symbol)
    return None
