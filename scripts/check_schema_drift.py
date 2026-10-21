"""Report model tables and columns the connected database is missing. Read-only.

    python scripts/check_schema_drift.py            # uses DATABASE_URL
    docker exec -i tb-backend python /libs/tb-shared-lib/scripts/check_schema_drift.py

Exits 1 when anything is missing, so it can gate a deploy. Fix a gap with an Alembic migration,
never by editing the database by hand.
"""

import os
import sys

from sqlalchemy import create_engine

# Importing the package registers every model on Base.metadata; nothing in it is used by name.
import tb_utils.models  # noqa: F401  # pylint: disable=unused-import
from tb_utils.models.base import Base
from tb_utils.schema_drift import find_drift


def _sync_url(url: str) -> str:
    """The sync driver for a URL that may name an async one (asyncpg)."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.")
        return 2
    drift = find_drift(create_engine(_sync_url(url)), Base.metadata)
    if drift.clean:
        print("No drift: every model table and column exists in the database.")
        return 0
    for table in drift.missing_tables:
        print(f"MISSING TABLE   {table}")
    for table, columns in drift.missing_columns.items():
        print(f"MISSING COLUMNS {table}: {', '.join(columns)}")
    print("\nAdd an Alembic migration for each and run `alembic upgrade head`.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
