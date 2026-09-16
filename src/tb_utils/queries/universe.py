"""Tradable Universe query helpers.

The **Tradable Universe** is the union of:
    1. Symbols in ``fundamental_universe`` where ``is_active = True``.
    2. Symbols in ``instrument`` where ``is_fno = 1``.

All heavy data-ingestion pipelines (option chains, delivery data, news tagging,
historical backfills) should scope their work to this universe instead of
processing all 2,200+ master instruments.
"""

import logging

from sqlalchemy.orm import Session

from tb_utils.models.fundamental_universe import FundamentalUniverse
from tb_utils.models.instrument import Instrument

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
