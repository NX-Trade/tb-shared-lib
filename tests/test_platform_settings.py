"""Settings kept in the database: validated, versioned, audited, and failing closed."""

# pylint: disable=redefined-outer-name
import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tb_utils import platform_settings as ps
from tb_utils.models import PlatformSetting, PlatformSettingHistory

KEY = "stc_spread"


def row(value, version=1, updated_by="abhi"):
    return SimpleNamespace(
        key=KEY, value=value, version=version, updated_by=updated_by,
        updated_at=dt.datetime(2026, 10, 30, 9, 0, tzinfo=dt.UTC),
    )  # fmt: skip


class FakeDb:
    """Just what the loader and saver use: get, add, commit, rollback; records every write."""

    def __init__(self, stored=None, fail_reads=False):
        self.stored, self.fail_reads = stored, fail_reads
        self.added, self.commits, self.rollbacks = [], 0, 0

    def get(self, _model, _key):
        if self.fail_reads:
            raise ConnectionError("db down")
        return self.stored

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, PlatformSetting):
            self.stored = obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


# ── The model: defaults and validation ───────────────────────────────────────


def test_the_defaults_are_the_agreed_values():
    s = ps.StcSpreadSettings()
    assert (s.max_active_baskets, s.max_per_underlying) == (3, 1)
    assert (s.entry_start, s.entry_end) == ("09:30", "14:30")
    assert (s.eod_exit_time, s.hard_exit_time) == ("15:15", "15:29")
    assert (s.signal_max_age_minutes, s.refresh_timeout_seconds) == (10, 45)
    assert s.order_type == "MARKETABLE_LIMIT"


def test_every_settings_model_defaults_to_off():
    """Anything that fails to load falls back to its defaults, so those must never trade."""
    for model in ps.SETTING_MODELS.values():
        assert model().enabled is False


@pytest.mark.parametrize("bad", ["9:30", "0930", "25:00", "12:60", "", "ab:cd"])
def test_a_time_must_be_a_real_hh_mm(bad):
    with pytest.raises(ValueError):
        ps.StcSpreadSettings(entry_start=bad)


@pytest.mark.parametrize(
    "change",
    [
        {"entry_start": "14:30", "entry_end": "14:30"},  # the window has no width
        {"entry_end": "15:20"},  # entries still open when the exit has started
        {"eod_exit_time": "15:29"},  # no time between the exit starting and the hard deadline
        {"hard_exit_time": "15:30"},  # at the close, too late to fill
        {"hard_exit_time": "15:10"},  # hard deadline before the exit starts
    ],
)
def test_the_times_must_be_in_order(change):
    with pytest.raises(ValueError):
        ps.StcSpreadSettings(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"max_active_baskets": 0}, {"max_active_baskets": 21}, {"max_per_underlying": 0},
        {"signal_max_age_minutes": 0}, {"refresh_timeout_seconds": 5}, {"order_type": "STOP"},
        {"unknown_field": 1},
    ],
)  # fmt: skip
def test_out_of_range_or_unknown_values_are_refused(change):
    with pytest.raises(ValueError):
        ps.StcSpreadSettings(**change)


def test_a_time_is_read_back_as_a_time():
    assert ps.time_of("14:30") == dt.time(14, 30)


def test_the_stored_form_keeps_hh_mm_strings():
    assert ps.StcSpreadSettings().model_dump(mode="json")["entry_end"] == "14:30"


# ── Loading ──────────────────────────────────────────────────────────────────


def test_no_row_and_no_fallback_gives_the_defaults():
    loaded = ps.load_setting(FakeDb(), KEY)
    assert loaded.source == "default" and loaded.values.enabled is False and loaded.version == 0


def test_no_row_uses_the_service_fallback_and_says_so():
    loaded = ps.load_setting(FakeDb(), KEY, fallback={"enabled": True, "max_active_baskets": 1})
    assert loaded.source == "fallback"
    assert (loaded.values.enabled, loaded.values.max_active_baskets) == (True, 1)


def test_a_stored_row_wins_over_the_fallback():
    db = FakeDb(row({"enabled": False, "max_active_baskets": 2}, version=4))
    loaded = ps.load_setting(db, KEY, fallback={"enabled": True, "max_active_baskets": 1})
    assert loaded.source == "database" and loaded.version == 4
    assert (loaded.values.enabled, loaded.values.max_active_baskets) == (False, 2)


def test_a_row_with_only_some_keys_takes_the_rest_from_the_fallback():
    db = FakeDb(row({"enabled": True}))
    loaded = ps.load_setting(db, KEY, fallback={"max_active_baskets": 1})
    assert loaded.values.enabled is True and loaded.values.max_active_baskets == 1


def test_invalid_stored_data_fails_closed_and_ignores_a_fallback_that_says_on():
    """A corrupt row must never fall back to an env value that happens to be 'on'."""
    db = FakeDb(row({"enabled": True, "entry_end": "99:99"}))
    loaded = ps.load_setting(db, KEY, fallback={"enabled": True})
    assert loaded.source == "invalid" and loaded.values.enabled is False


def test_an_unreadable_database_fails_closed():
    loaded = ps.load_setting(FakeDb(fail_reads=True), KEY, fallback={"enabled": True})
    assert loaded.source == "error" and loaded.values.enabled is False


def test_an_invalid_fallback_is_ignored_not_trusted():
    loaded = ps.load_setting(FakeDb(), KEY, fallback={"enabled": True, "entry_end": "bad"})
    assert loaded.source == "invalid" and loaded.values.enabled is False


def test_an_unknown_key_is_an_error():
    with pytest.raises(ps.SettingError, match="unknown"):
        ps.load_setting(FakeDb(), "nope")


# ── Saving ───────────────────────────────────────────────────────────────────


def test_the_first_save_creates_version_one_and_a_history_row():
    db = FakeDb()
    saved = ps.save_setting(db, KEY, {"enabled": True, "max_active_baskets": 1}, updated_by="abhi")
    assert saved.version == 1 and saved.source == "database" and saved.values.enabled is True
    stored = [o for o in db.added if isinstance(o, PlatformSetting)][0]
    history = [o for o in db.added if isinstance(o, PlatformSettingHistory)][0]
    assert (stored.key, stored.version, stored.updated_by) == (KEY, 1, "abhi")
    assert history.old_value is None and history.new_value["enabled"] is True
    assert (history.changed_by, history.version) == ("abhi", 1)
    assert db.commits == 1


def test_a_later_save_bumps_the_version_and_keeps_the_old_value_in_history():
    db = FakeDb(row({"enabled": False, "max_active_baskets": 3}, version=2))
    saved = ps.save_setting(db, KEY, {"enabled": True}, updated_by="abhi")
    assert saved.version == 3
    history = [o for o in db.added if isinstance(o, PlatformSettingHistory)][0]
    assert history.old_value["enabled"] is False and history.new_value["enabled"] is True
    assert history.version == 3


def test_a_partial_change_keeps_every_other_effective_value():
    db = FakeDb()
    saved = ps.save_setting(
        db, KEY, {"max_active_baskets": 1}, updated_by="abhi", fallback={"entry_end": "14:00"}
    )
    assert saved.values.max_active_baskets == 1 and saved.values.entry_end == "14:00"


def test_an_invalid_change_is_refused_and_writes_nothing():
    db = FakeDb()
    with pytest.raises(ps.SettingValidationError) as exc:
        ps.save_setting(db, KEY, {"entry_end": "15:20"}, updated_by="abhi")
    assert exc.value.errors and not db.added and db.commits == 0


def test_a_stale_version_is_a_conflict_and_writes_nothing():
    db = FakeDb(row({"enabled": False}, version=5))
    with pytest.raises(ps.SettingConflict):
        ps.save_setting(db, KEY, {"enabled": True}, updated_by="abhi", expected_version=4)
    assert not db.added and db.commits == 0


def test_the_expected_version_is_optional_and_checked_when_given():
    db = FakeDb(row({}, version=5))
    saved = ps.save_setting(db, KEY, {"enabled": False}, updated_by="abhi", expected_version=5)
    assert saved.version == 6


def test_a_save_needs_to_say_who_made_it():
    with pytest.raises(ps.SettingError, match="updated_by"):
        ps.save_setting(FakeDb(), KEY, {"enabled": True}, updated_by="  ")


def test_a_corrupt_stored_value_can_be_overwritten_with_a_valid_one():
    db = FakeDb(row({"entry_end": "99:99"}, version=3))
    saved = ps.save_setting(db, KEY, {"enabled": False}, updated_by="abhi")
    assert saved.version == 4 and saved.source == "database"


def test_an_unreadable_database_refuses_a_save():
    with pytest.raises(ps.SettingError):
        ps.save_setting(FakeDb(fail_reads=True), KEY, {"enabled": True}, updated_by="abhi")


def test_a_failed_commit_is_rolled_back_and_reported():
    db = FakeDb()
    db.commit = MagicMock(side_effect=RuntimeError("write failed"))
    with pytest.raises(RuntimeError):
        ps.save_setting(db, KEY, {"enabled": True}, updated_by="abhi")
    assert db.rollbacks == 1


# ── The tables ───────────────────────────────────────────────────────────────


def test_the_tables_have_the_columns_the_api_and_audit_need():
    assert [c.name for c in PlatformSetting.__table__.primary_key.columns] == ["key"]
    for column in ("value", "version", "updated_by", "updated_at"):
        assert column in PlatformSetting.__table__.c
    for column in ("key", "version", "old_value", "new_value", "changed_by", "changed_at"):
        assert column in PlatformSettingHistory.__table__.c
