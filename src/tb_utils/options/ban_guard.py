"""Is this underlying in the F&O ban period? Answers fail closed.

NSE bans *fresh* positions in a security that crosses the market-wide position limit. A spread opens
two fresh positions, so an entry on a banned name must not go out. The collector syncs the list at
09:00 IST and records the day it synced for; this guard trusts a list only if it is proven to be
today's.

Three answers, and only one of them opens the gate:

* ``BANNED``  - today's list names the symbol.
* ``CLEAR``   - today's list was synced and the symbol is not on it. An empty list counts: "nobody
  is banned" is a fact about a sync that ran, not a lack of data.
* ``UNKNOWN`` - there is no proof of a sync for today (it failed, has not run yet, or Redis and the
  database both cannot be read). Treated as blocked, because the cost of waiting is a missed trade
  and the cost of guessing is an order the exchange rejects or a position that cannot be exited.

Exits are never gated by this: closing a position is allowed during a ban, and callers only consult
the guard when opening one.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from tb_utils.models import FnoBanList, FnoBanSync
from tb_utils.options.pcr import is_pcr_symbol
from tb_utils.redis.sync_market_store import SyncMarketStore

logger = logging.getLogger("tb_utils.options.ban_guard")

BANNED = "BANNED"
CLEAR = "CLEAR"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BanSnapshot:
    """The ban list and the trading day it is for."""

    trade_date: dt.date
    symbols: frozenset[str]


@dataclass(frozen=True)
class BanStatus:
    state: str  # BANNED | CLEAR | UNKNOWN
    symbol: str
    detail: str
    trade_date: Optional[dt.date] = None  # the day of the list that decided it

    @property
    def allows_entry(self) -> bool:
        return self.state == CLEAR


def normalize(symbol: str) -> str:
    return (symbol or "").strip().upper()


def evaluate(symbol: str, snapshot: Optional[BanSnapshot], today: dt.date) -> BanStatus:
    """The pure decision. No I/O, so every branch is tested without a database."""
    clean = normalize(symbol)
    if is_pcr_symbol(clean):  # index options are not subject to the stock ban list
        return BanStatus(CLEAR, clean, "index options are not subject to the F&O ban list")
    if snapshot is None:
        return BanStatus(
            UNKNOWN, clean, f"no ban list is proven synced for {today}: treating {clean} as blocked"
        )
    if snapshot.trade_date != today:
        detail = (
            f"the latest ban list is for {snapshot.trade_date}, not {today}: "
            f"treating {clean} as blocked"
        )
        return BanStatus(UNKNOWN, clean, detail, snapshot.trade_date)
    if clean in snapshot.symbols:
        return BanStatus(BANNED, clean, f"{clean} is in the F&O ban period on {today}", today)
    return BanStatus(CLEAR, clean, f"{clean} is not in the F&O ban list for {today}", today)


def _from_store(store: SyncMarketStore) -> Optional[BanSnapshot]:
    found = store.get_fno_ban_snapshot()
    if found is None:
        return None
    symbols, trade_date = found
    return BanSnapshot(trade_date, frozenset(normalize(s) for s in symbols))


def _from_db(db: Session, today: dt.date) -> Optional[BanSnapshot]:
    """Today's list from Postgres, only if a sync row proves it was synced today."""
    if db.get(FnoBanSync, today) is None:
        return None
    rows = db.query(FnoBanList.symbol).filter(FnoBanList.trade_date == today).all()
    return BanSnapshot(today, frozenset(normalize(row[0]) for row in rows))


def load_snapshot(
    store: Optional[SyncMarketStore], db: Optional[Session], today: dt.date
) -> Optional[BanSnapshot]:
    """Today's ban list from Redis, else from Postgres; None if neither can prove it.

    Any read error is logged and skipped, never raised: the caller's answer is then UNKNOWN.
    """
    if store is not None:
        try:
            snapshot = _from_store(store)
            if snapshot is not None and snapshot.trade_date == today:
                return snapshot
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("[ban_guard] Redis read failed; falling back to the database.")
    if db is not None:
        try:
            return _from_db(db, today)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("[ban_guard] database read failed.")
    return None


def check_symbol(
    symbol: str,
    today: dt.date,
    store: Optional[SyncMarketStore] = None,
    db: Optional[Session] = None,
) -> BanStatus:
    """Whether a new F&O position may be opened on ``symbol`` today."""
    return evaluate(symbol, load_snapshot(store, db, today), today)


__all__ = [
    "BANNED",
    "CLEAR",
    "UNKNOWN",
    "BanSnapshot",
    "BanStatus",
    "check_symbol",
    "evaluate",
    "load_snapshot",
    "normalize",
]
