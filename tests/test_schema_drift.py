# pylint: disable=redefined-outer-name,wrong-import-order  # fixtures by name; ruff sorts alembic first
"""schema_drift: model columns the live database lacks, and the trade.unrealized_pnl regression."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, text

from tb_utils.models import Trade
from tb_utils.schema_drift import find_drift

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE widget (id INTEGER PRIMARY KEY, name TEXT)"))
    return engine


def _metadata(*columns, table="widget"):
    metadata = MetaData()
    Table(table, metadata, Column("id", Integer, primary_key=True), *columns)
    return metadata


def test_a_matching_schema_is_clean(engine):
    drift = find_drift(engine, _metadata(Column("name", String)))
    assert drift.clean and not drift.missing_tables and not drift.missing_columns


def test_a_model_column_the_database_lacks_is_reported(engine):
    drift = find_drift(engine, _metadata(Column("name", String), Column("unrealized_pnl", Integer)))
    assert not drift.clean
    assert drift.missing_columns == {"widget": ["unrealized_pnl"]}


def test_every_missing_column_of_a_table_is_listed(engine):
    drift = find_drift(engine, _metadata(Column("a", Integer), Column("b", Integer)))
    assert drift.missing_columns == {"widget": ["a", "b"]}


def test_a_table_the_database_lacks_is_reported(engine):
    drift = find_drift(engine, _metadata(table="gadget"))
    assert drift.missing_tables == ["gadget"] and not drift.missing_columns


def test_extra_database_columns_are_not_drift(engine):
    assert find_drift(engine, _metadata()).clean  # the table also has `name`, which the model omits


def test_it_is_read_only(engine):
    find_drift(engine, _metadata(Column("new_col", Integer)))
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(widget)"))]
    assert columns == ["id", "name"]


class TestTradeUnrealizedPnl:
    def test_the_model_declares_it(self):
        assert "unrealized_pnl" in Trade.__table__.columns

    def test_a_migration_adds_it_to_trade(self):
        scripts = ScriptDirectory.from_config(_config())
        sources = [Path(rev.path).read_text(encoding="utf-8") for rev in scripts.walk_revisions()]
        assert any(
            "ADD COLUMN IF NOT EXISTS unrealized_pnl" in s and "trade" in s.lower() for s in sources
        )

    def test_the_migration_is_idempotent_and_reversible(self):
        text_ = (ALEMBIC_DIR / "versions" / "q1f2a3b4c5d7_add_trade_unrealized_pnl.py").read_text(
            encoding="utf-8"
        )
        assert "ADD COLUMN IF NOT EXISTS" in text_ and "DROP COLUMN IF EXISTS" in text_

    def test_it_is_the_single_head(self):
        assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config
