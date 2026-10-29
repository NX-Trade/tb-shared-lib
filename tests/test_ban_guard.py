"""The F&O ban guard fails closed: only a list proven current for today can clear an entry."""

import datetime as dt
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tb_utils.options import ban_guard as bg
from tb_utils.redis.keys import get_fno_ban_list_key, get_fno_ban_meta_key
from tb_utils.redis.sync_market_store import SyncMarketStore

TODAY = dt.date(2026, 10, 29)
YESTERDAY = TODAY - dt.timedelta(days=1)


def snapshot(symbols=("SAIL", "KAYNES"), trade_date=TODAY):
    return bg.BanSnapshot(trade_date, frozenset(symbols))


# ── The pure decision ────────────────────────────────────────────────────────


def test_a_banned_symbol_is_banned():
    status = bg.evaluate("SAIL", snapshot(), TODAY)
    assert status.state == bg.BANNED and not status.allows_entry
    assert "SAIL" in status.detail


def test_a_symbol_missing_from_todays_list_is_clear():
    status = bg.evaluate("INFY", snapshot(), TODAY)
    assert status.state == bg.CLEAR and status.allows_entry


def test_an_empty_list_is_clear_only_because_it_was_synced_today():
    """'Nobody is banned' is a fact about a sync, not an absence of data."""
    assert bg.evaluate("INFY", snapshot(symbols=()), TODAY).state == bg.CLEAR


def test_no_snapshot_means_unknown_and_blocks():
    status = bg.evaluate("INFY", None, TODAY)
    assert status.state == bg.UNKNOWN and not status.allows_entry
    assert "no ban list" in status.detail.lower()


def test_a_list_synced_for_another_day_is_not_trusted():
    status = bg.evaluate("INFY", snapshot(trade_date=YESTERDAY), TODAY)
    assert status.state == bg.UNKNOWN and not status.allows_entry
    assert str(YESTERDAY) in status.detail


def test_a_banned_name_on_a_stale_list_is_still_unknown_not_banned():
    """We do not know about today, so we do not claim to."""
    assert bg.evaluate("SAIL", snapshot(trade_date=YESTERDAY), TODAY).state == bg.UNKNOWN


@pytest.mark.parametrize("raw", ["sail", " SAIL ", "Sail"])
def test_symbols_are_normalised_before_matching(raw):
    assert bg.evaluate(raw, snapshot(), TODAY).state == bg.BANNED


@pytest.mark.parametrize("index", ["NIFTY50", "NIFTY", "BANKNIFTY", "finnifty"])
def test_indices_are_never_in_the_stock_ban_list(index):
    """Index options are not subject to it, so a missing list must not block them."""
    assert bg.evaluate(index, None, TODAY).state == bg.CLEAR


# ── Loading the snapshot ─────────────────────────────────────────────────────


def store_with(snap):
    store = MagicMock()
    store.get_fno_ban_snapshot.return_value = (
        None if snap is None else (sorted(snap.symbols), snap.trade_date)
    )
    return store


def db_with(sync_row, symbols=()):
    db = MagicMock()
    db.get.return_value = sync_row
    db.query.return_value.filter.return_value.all.return_value = [(s,) for s in symbols]
    return db


def test_a_current_redis_snapshot_is_used_without_touching_the_database():
    db = db_with(None)
    snap = bg.load_snapshot(store_with(snapshot()), db, TODAY)
    assert snap == snapshot()
    db.get.assert_not_called()


def test_a_stale_redis_snapshot_falls_back_to_the_database():
    db = db_with(SimpleNamespace(trade_date=TODAY), symbols=["SAIL"])
    snap = bg.load_snapshot(store_with(snapshot(trade_date=YESTERDAY)), db, TODAY)
    assert snap == snapshot(symbols=("SAIL",))


def test_a_missing_redis_snapshot_falls_back_to_the_database():
    db = db_with(SimpleNamespace(trade_date=TODAY), symbols=[])
    assert bg.load_snapshot(store_with(None), db, TODAY) == snapshot(symbols=())


def test_a_redis_error_falls_back_to_the_database():
    store = MagicMock()
    store.get_fno_ban_snapshot.side_effect = ConnectionError("redis down")
    db = db_with(SimpleNamespace(trade_date=TODAY), symbols=["KAYNES"])
    assert bg.load_snapshot(store, db, TODAY) == snapshot(symbols=("KAYNES",))


def test_no_sync_marker_for_today_means_no_snapshot_even_if_old_rows_exist():
    """Rows from earlier days must never be read as today's list."""
    assert bg.load_snapshot(store_with(None), db_with(None, symbols=["SAIL"]), TODAY) is None


def test_every_source_failing_means_no_snapshot_not_an_exception():
    store = MagicMock()
    store.get_fno_ban_snapshot.side_effect = ConnectionError("redis down")
    db = MagicMock()
    db.get.side_effect = RuntimeError("db down")
    assert bg.load_snapshot(store, db, TODAY) is None


def test_check_symbol_ties_loading_and_deciding_together():
    db = db_with(SimpleNamespace(trade_date=TODAY), symbols=["SAIL"])
    assert bg.check_symbol("SAIL", TODAY, store_with(None), db).state == bg.BANNED
    assert bg.check_symbol("INFY", TODAY, store_with(None), db).state == bg.CLEAR
    assert bg.check_symbol("INFY", TODAY, store_with(None), db_with(None)).state == bg.UNKNOWN


# ── The Redis snapshot ───────────────────────────────────────────────────────


def test_the_snapshot_key_is_namespaced_next_to_the_list():
    assert get_fno_ban_meta_key() == "market_data:fno_ban_list:meta"


def test_store_writes_the_list_and_its_trade_date_together():
    client = MagicMock()
    SyncMarketStore(client).store_fno_ban_snapshot(["SAIL", "KAYNES"], TODAY, expiry_seconds=100)
    pipe = client.pipeline.return_value
    writes = {call.args[0]: call.args for call in pipe.setex.call_args_list}
    assert json.loads(writes[get_fno_ban_list_key()][2]) == ["SAIL", "KAYNES"]
    assert json.loads(writes[get_fno_ban_meta_key()][2]) == {"trade_date": "2026-10-29"}
    pipe.execute.assert_called_once()


def test_an_empty_ban_list_is_still_written():
    client = MagicMock()
    SyncMarketStore(client).store_fno_ban_snapshot([], TODAY)
    pipe = client.pipeline.return_value
    assert pipe.setex.call_count == 2


def test_reading_returns_the_list_and_its_date():
    client = MagicMock()
    client.get.side_effect = {
        get_fno_ban_list_key(): json.dumps(["SAIL"]),
        get_fno_ban_meta_key(): json.dumps({"trade_date": "2026-10-29"}),
    }.get
    assert SyncMarketStore(client).get_fno_ban_snapshot() == (["SAIL"], TODAY)


def test_reading_an_empty_list_is_not_the_same_as_a_missing_one():
    client = MagicMock()
    client.get.side_effect = {
        get_fno_ban_list_key(): "[]",
        get_fno_ban_meta_key(): json.dumps({"trade_date": "2026-10-29"}),
    }.get
    assert SyncMarketStore(client).get_fno_ban_snapshot() == ([], TODAY)


def test_a_list_without_its_marker_is_not_a_snapshot():
    """The old key alone (written before the marker existed) proves nothing about today."""
    client = MagicMock()
    client.get.side_effect = {get_fno_ban_list_key(): json.dumps(["SAIL"])}.get
    assert SyncMarketStore(client).get_fno_ban_snapshot() is None


def test_a_corrupt_marker_is_not_a_snapshot():
    client = MagicMock()
    client.get.side_effect = {
        get_fno_ban_list_key(): "[]",
        get_fno_ban_meta_key(): "not json",
    }.get
    assert SyncMarketStore(client).get_fno_ban_snapshot() is None
