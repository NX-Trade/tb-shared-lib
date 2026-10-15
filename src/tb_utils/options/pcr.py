"""Put-Call Ratio interpretation.

PCR (put OI / call OI) is only treated as a market signal for indices. On a
single stock it mostly reflects hedging and positioning noise, so callers
should gate on ``is_pcr_symbol`` before using it.

Zones, high to low:

* ``> 1.6``  heavily bullish. Crowded: when India VIX is also rising through
  16-18 the rally is vulnerable, so it is a cue to book profits (see
  ``is_euphoria_risk``).
* ``> 1.2``  moderately bullish
* ``> 1.0``  bullish
* ``== 1.0`` neutral
* ``< 1.0``  bearish
* ``< 0.8``  more bearish
* ``< 0.5``  heavily bearish. Oversold, so a reversal becomes likely.
"""

from enum import StrEnum
from typing import Optional

PCR_HEAVILY_BULLISH_MIN: float = 1.6
PCR_MODERATELY_BULLISH_MIN: float = 1.2
PCR_BULLISH_MIN: float = 1.0
PCR_MORE_BEARISH_MAX: float = 0.8
PCR_HEAVILY_BEARISH_MAX: float = 0.5

# India VIX at or above this, while rising, turns a heavily bullish PCR from
# "strong market" into "book profits". At or above the high mark the warning
# is stronger.
VIX_EUPHORIA_WARN: float = 16.0
VIX_EUPHORIA_HIGH: float = 18.0

# DB/option_chain names for the indices PCR is meaningful for.
PCR_INDEX_SYMBOLS = frozenset(
    {
        "NIFTY",
        "NIFTY50",
        "BANKNIFTY",
        "FINNIFTY",
        "NSEFIN",
        "MIDCPNIFTY",
        "MIDCAPSEL",
        "NIFTYNEXT50",
        "NIFTYNXT50",
    }
)


class PcrZone(StrEnum):
    HEAVILY_BULLISH = "HEAVILY_BULLISH"
    MODERATELY_BULLISH = "MODERATELY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    MORE_BEARISH = "MORE_BEARISH"
    HEAVILY_BEARISH = "HEAVILY_BEARISH"


def is_pcr_symbol(symbol: str) -> bool:
    """True for indices, the only symbols where PCR is a usable signal."""
    return symbol.upper() in PCR_INDEX_SYMBOLS


def classify_pcr(pcr: float) -> PcrZone:
    """Map a PCR value onto its sentiment zone."""
    if pcr == PCR_BULLISH_MIN:
        return PcrZone.NEUTRAL
    if pcr > PCR_BULLISH_MIN:
        above = [
            (PCR_HEAVILY_BULLISH_MIN, PcrZone.HEAVILY_BULLISH),
            (PCR_MODERATELY_BULLISH_MIN, PcrZone.MODERATELY_BULLISH),
        ]
        return next((zone for floor, zone in above if pcr > floor), PcrZone.BULLISH)
    below = [
        (PCR_HEAVILY_BEARISH_MAX, PcrZone.HEAVILY_BEARISH),
        (PCR_MORE_BEARISH_MAX, PcrZone.MORE_BEARISH),
    ]
    return next((zone for ceiling, zone in below if pcr < ceiling), PcrZone.BEARISH)


def is_oversold_reversal(pcr: float) -> bool:
    """Heavily bearish PCR: sentiment is washed out and a bounce is likely."""
    return classify_pcr(pcr) is PcrZone.HEAVILY_BEARISH


def is_euphoria_risk(pcr: float, vix: Optional[float], vix_change: Optional[float] = None) -> bool:
    """Heavily bullish PCR while India VIX is climbing: a good time to book profits.

    Args:
        pcr: Index put-call ratio.
        vix: Latest India VIX. ``None`` (no reading) never triggers.
        vix_change: Day's VIX change in points. When given it must be positive
            (VIX rising); when ``None`` only the level is checked.
    """
    if vix is None or classify_pcr(pcr) is not PcrZone.HEAVILY_BULLISH:
        return False
    if vix < VIX_EUPHORIA_WARN:
        return False
    return vix_change is None or vix_change > 0
