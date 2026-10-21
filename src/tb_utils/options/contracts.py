"""Option contract identity: the exchange symbol a broker order needs.

An option is stored in this codebase as ``(underlying, expiry, strike, type)``. Upstox resolves an
order from a compact symbol, ``UNDERLYING + YY + MON + DD + STRIKE + TYPE`` (for example
``NIFTY26NOV0322800CE``), and its instrument master registers that *with-day* form for **every**
option, weekly and monthly alike, so it is the one spelling that never needs a guess about which
expiry is the monthly. Pure functions: no DB, no Redis, no HTTP.
"""

# stdlib
import datetime as dt
import re
from dataclasses import dataclass
from typing import Optional

MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# Our stored symbol for an index is not the exchange's underlying name.
EXCHANGE_UNDERLYING = {"NIFTY50": "NIFTY"}

_SYMBOL = re.compile(
    r"^(?P<underlying>.+?)(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})"
    r"(?P<strike>\d+(?:\.\d+)?)(?P<kind>CE|PE)$"
)


@dataclass(frozen=True)
class ContractParts:
    underlying: str
    expiry: dt.date
    strike: float
    option_type: str


def exchange_underlying(symbol: str) -> str:
    """The underlying's name as the exchange spells it (``NIFTY50`` -> ``NIFTY``)."""
    return EXCHANGE_UNDERLYING.get(symbol.upper(), symbol.upper())


def stored_underlying(symbol: str) -> str:
    """The name our own tables use for an exchange underlying (``NIFTY`` -> ``NIFTY50``)."""
    symbol = symbol.upper()
    return next((ours for ours, theirs in EXCHANGE_UNDERLYING.items() if theirs == symbol), symbol)


def _strike_text(strike: float) -> str:
    return f"{strike:.2f}".rstrip("0").rstrip(".")


def option_contract_symbol(
    underlying: str, expiry: dt.date, strike: float, option_type: str
) -> str:
    """``NIFTY26NOV0322800CE``: the compact with-day symbol of one option contract."""
    if option_type not in ("CE", "PE"):
        raise ValueError(f"option_type must be CE or PE, got {option_type!r}")
    if strike <= 0:
        raise ValueError(f"strike must be positive, got {strike}")
    return (
        f"{exchange_underlying(underlying)}{expiry:%y}{MONTHS[expiry.month - 1]}"
        f"{expiry:%d}{_strike_text(strike)}{option_type}"
    )


def parse_option_contract_symbol(symbol: str) -> Optional[ContractParts]:
    """Read a compact with-day symbol back into its parts, or None if it is not one."""
    match = _SYMBOL.match(symbol.strip().upper())
    if not match or match["mon"] not in MONTHS:
        return None
    try:
        expiry = dt.date(2000 + int(match["yy"]), MONTHS.index(match["mon"]) + 1, int(match["dd"]))
    except ValueError:
        return None
    return ContractParts(match["underlying"], expiry, float(match["strike"]), match["kind"])
