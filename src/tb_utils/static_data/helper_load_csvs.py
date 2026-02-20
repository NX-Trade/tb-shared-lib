"""Static data CSV loader for PostgreSQL via SQLAlchemy.

Loads bootstrap/static CSV data (instruments, FII/DII) into the PostgreSQL
database using the SQLAlchemy models defined in tb_utils.
"""

import csv
import logging
import os
from typing import List

from tb_utils.config.db_session import get_session_factory
from tb_utils.models import FiiDii, Instrument

logger = logging.getLogger(__name__)

# Default CSV file names — resolved relative to this file's directory
_HERE = os.path.dirname(os.path.abspath(__file__))
NIFTY_500_CSV = os.path.join(_HERE, "Nifty500_list.csv")
FII_DII_CSV = os.path.join(_HERE, "fii_dii_cash.csv")


def _read_csv(filepath: str) -> List[dict]:
    """Read a CSV file and return a list of row dicts.

    Args:
        filepath: Absolute path to the CSV file

    Returns:
        List of dicts, one per row
    """
    with open(filepath, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_nifty_500(csv_path: str = NIFTY_500_CSV) -> int:
    """Load Nifty 500 instrument data from CSV into the Instrument table.

    Skips rows that already exist (matched by 'symbol' column).

    Args:
        csv_path: Path to the Nifty500_list.csv file

    Returns:
        Number of rows inserted
    """
    rows = _read_csv(csv_path)
    inserted = 0
    SessionFactory = get_session_factory()

    with SessionFactory() as db:
        for row in rows:
            symbol = row.get("symbol") or row.get("Symbol")
            if not symbol:
                logger.warning("Skipping row with no symbol: %s", row)
                continue

            exists = db.query(Instrument).filter_by(symbol=symbol).first()
            if exists:
                logger.debug("Instrument %s already exists — skipping.", symbol)
                continue

            instrument = Instrument(**{k.lower(): v for k, v in row.items()})
            db.add(instrument)
            inserted += 1

        db.commit()

    logger.info("Nifty 500 load complete: %d rows inserted.", inserted)
    return inserted


def load_fii_dii(csv_path: str = FII_DII_CSV) -> int:
    """Load FII/DII cash market data from CSV into the FiiDii table.

    Args:
        csv_path: Path to the fii_dii_cash.csv file

    Returns:
        Number of rows inserted
    """
    rows = _read_csv(csv_path)
    inserted = 0
    SessionFactory = get_session_factory()

    with SessionFactory() as db:
        for row in rows:
            record = FiiDii(**{k.lower(): v for k, v in row.items()})
            db.add(record)
            inserted += 1

        db.commit()

    logger.info("FII/DII load complete: %d rows inserted.", inserted)
    return inserted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    load_nifty_500()
    load_fii_dii()
