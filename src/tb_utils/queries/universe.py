"""Tradable Universe query helpers.

The **Tradable Universe** is the union of:
    1. Symbols in ``fundamental_universe`` where ``is_active = True``.
    2. Symbols in ``instrument`` where ``is_fno = 1``.

All heavy data-ingestion pipelines (option chains, delivery data, news tagging,
historical backfills) should scope their work to this universe instead of
processing all 2,200+ master instruments.
"""

import logging
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from tb_utils.models.fundamental_universe import FundamentalUniverse
from tb_utils.models.instrument import Instrument
from tb_utils.models.nse_reference import Nifty500AsOfDate

logger = logging.getLogger(__name__)


def get_tradable_symbols(db: Session) -> set[str]:
    """Return the set of symbols in the Tradable Universe.

    Tradable Universe = {active fundamental_universe symbols}
                        ∪ {instruments with is_fno = 1}

    Returns:
        Set of uppercase symbol strings.  Returns an empty set only when
        both sources are empty (should not happen in production).
    """
    fno_symbols: set[str] = {
        r[0] for r in db.query(Instrument.symbol).filter(Instrument.is_fno == 1).all()
    }
    fund_symbols: set[str] = {
        r[0]
        for r in db.query(FundamentalUniverse.symbol)
        .filter(FundamentalUniverse.is_active.is_(True))
        .all()
    }
    combined = fno_symbols | fund_symbols
    logger.info(
        "Tradable Universe: %d symbols (F&O=%d, Fundamental=%d, overlap=%d).",
        len(combined),
        len(fno_symbols),
        len(fund_symbols),
        len(fno_symbols & fund_symbols),
    )
    return combined


def get_nifty500_members_as_of(db: Session, as_of: date) -> list[str]:
    """Return Nifty 500 membership **as it stood on** ``as_of``.

    Point-in-time membership matters whenever history is used to fit or evaluate
    a model, and there are two opposite ways to get it wrong:

    * filtering ``instrument.is_nifty_500`` uses *today's* index — survivorship
      bias, because every symbol since dropped disappears from the past and
      flatters any backtest;
    * taking every row with ``as_of_date <= as_of`` is the union of everyone who
      was *ever* a member, so a stock dropped three years ago is still scored.

    The correct set is the most recent snapshot at or before ``as_of``.

    Args:
        db: Active session.
        as_of: The date to reconstruct membership for.

    Returns:
        Sorted symbols, or an empty list when no snapshot exists at or before
        ``as_of`` — callers should then fall back explicitly rather than
        silently inheriting today's index.
    """
    snapshot_date = (
        db.query(func.max(Nifty500AsOfDate.as_of_date))
        .filter(Nifty500AsOfDate.as_of_date <= as_of)
        .scalar()
    )
    if snapshot_date is None:
        logger.warning("No nifty_500_as_of_date snapshot at or before %s.", as_of)
        return []

    rows = (
        db.query(Nifty500AsOfDate.symbol)
        .filter(
            Nifty500AsOfDate.as_of_date == snapshot_date,
            Nifty500AsOfDate.is_member == 1,
        )
        .all()
    )
    symbols = sorted({r[0] for r in rows})
    logger.info("Nifty 500 as of %s: %d symbols (snapshot %s).", as_of, len(symbols), snapshot_date)
    return symbols


def get_tradable_fno_symbols(db: Session) -> list[str]:
    """Return F&O symbols that are also in the Tradable Universe.

    This is the intersection: {is_fno = 1} ∩ {active fundamental_universe}.
    Falls back to *all* F&O symbols when fundamental_universe is empty
    (e.g. first deployment before screener sync has run).

    Returns:
        Sorted list of symbol strings suitable for option chain ingestion.
    """
    fno_symbols: set[str] = {
        r[0] for r in db.query(Instrument.symbol).filter(Instrument.is_fno == 1).all()
    }
    fund_symbols: set[str] = {
        r[0]
        for r in db.query(FundamentalUniverse.symbol)
        .filter(FundamentalUniverse.is_active.is_(True))
        .all()
    }

    if not fund_symbols:
        logger.warning(
            "fundamental_universe is empty — falling back to all %d F&O symbols.",
            len(fno_symbols),
        )
        return sorted(fno_symbols)

    filtered = fno_symbols & fund_symbols
    logger.info(
        "Tradable F&O symbols: %d (from %d F&O ∩ %d fundamental).",
        len(filtered),
        len(fno_symbols),
        len(fund_symbols),
    )
    return sorted(filtered)
