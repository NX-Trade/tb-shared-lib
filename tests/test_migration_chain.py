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


def test_segment_flags_migration_follows_the_previous_head_and_does_not_backfill():
    """Owner decision: the flags default off and existing accounts are NOT backfilled."""
    revision = _scripts().get_revision("u1a2b3c4d5f1")
    assert revision.down_revision == "t1a2b3c4d5f0"
    source = (
        ALEMBIC_DIR / "versions" / "u1a2b3c4d5f1_add_trading_segment_flags_to_client_account.py"
    ).read_text(encoding="utf-8")
    assert source.count("add_column") == 3
    assert source.count("server_default='false'") == 3
    assert "UPDATE" not in source.upper().replace("UPGRADE", "")


def test_ban_sync_migration_follows_the_segment_flags_migration():
    revision = _scripts().get_revision("v1a2b3c4d5f2")
    assert revision.down_revision == "u1a2b3c4d5f1"
    source = (ALEMBIC_DIR / "versions" / "v1a2b3c4d5f2_add_fno_ban_sync.py").read_text(
        encoding="utf-8"
    )
    assert "create_table" in source and "fno_ban_sync" in source
    assert "drop_table" in source


def test_there_is_still_a_single_head_after_the_ban_sync_migration():
    assert len(_scripts().get_heads()) == 1


def test_platform_settings_migration_follows_the_ban_sync_migration():
    revision = _scripts().get_revision("w1a2b3c4d5f3")
    assert revision.down_revision == "v1a2b3c4d5f2"
    source = (ALEMBIC_DIR / "versions" / "w1a2b3c4d5f3_add_platform_setting.py").read_text(
        encoding="utf-8"
    )
    assert source.count("create_table") == 2 and "platform_setting_history" in source
    assert source.count("drop_table") == 2


def test_there_is_a_single_head_after_the_platform_settings_migration():
    assert _scripts().get_heads() == ["w1a2b3c4d5f3"]
