"""The Alembic chain stays linear, and the idea-table drop is safe to run on any database."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


def _scripts() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return ScriptDirectory.from_config(config)


def test_there_is_a_single_head():
    """A second head would make `alembic upgrade head` refuse to run on optiplex."""
    assert len(_scripts().get_heads()) == 1


def test_the_idea_tables_are_dropped_after_the_trade_column_fix():
    assert _scripts().get_revision("r1f2a3b4c5d8").down_revision == "q1f2a3b4c5d7"


def test_dropping_the_idea_tables_is_idempotent():
    source = (ALEMBIC_DIR / "versions" / "r1f2a3b4c5d8_drop_option_idea_tables.py").read_text(
        encoding="utf-8"
    )
    assert source.count("DROP TABLE IF EXISTS") == 2
