"""Find columns the models declare that a live database does not have.

A model column with no migration behind it breaks every query that selects the model
(``column trade.unrealized_pnl does not exist``) while all the tests, which run on the models,
stay green. This compares the models' tables with the database's own catalogue and reports what
is missing. Read-only: it only inspects, and never alters anything.

Only *missing* tables and columns are reported. Extra columns in the database are harmless to the
ORM and often deliberate (a column kept after a model change), so they are not drift here.
"""

# stdlib
from dataclasses import dataclass, field

# third-party
from sqlalchemy import MetaData, inspect
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class Drift:
    missing_tables: list[str] = field(default_factory=list)
    missing_columns: dict[str, list[str]] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.missing_tables and not self.missing_columns


def find_drift(engine: Engine, metadata: MetaData) -> Drift:
    """Tables and columns declared by ``metadata`` that ``engine``'s database lacks."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    for name, table in sorted(metadata.tables.items()):
        if name not in existing:
            missing_tables.append(name)
            continue
        have = {column["name"] for column in inspector.get_columns(name)}
        lacking = [column.name for column in table.columns if column.name not in have]
        if lacking:
            missing_columns[name] = lacking
    return Drift(missing_tables, missing_columns)
