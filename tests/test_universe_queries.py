"""Point-in-time Nifty 500 membership.

Reconstructing a historical universe has two opposite failure modes, and the
codebase had the second one:

* filtering ``instrument.is_nifty_500`` uses *today's* index — survivorship
  bias, since anything since dropped vanishes from the past;
* taking every row with ``as_of_date <= as_of`` is the union of everyone who was
  *ever* a member, so a stock dropped years ago is still scored today.

The correct answer is the most recent snapshot at or before ``as_of``.
"""

from datetime import date
from unittest.mock import MagicMock

from tb_utils.queries.universe import get_nifty500_members_as_of


def _session(snapshot_date, symbols):
    """Session whose first query returns MAX(as_of_date) and second the symbols."""
    db = MagicMock()
    max_query = MagicMock()
    max_query.filter.return_value.scalar.return_value = snapshot_date
    symbol_query = MagicMock()
    symbol_query.filter.return_value.all.return_value = [(s,) for s in symbols]
    db.query.side_effect = [max_query, symbol_query]
    return db


def test_returns_members_of_the_latest_snapshot_at_or_before_the_date():
    db = _session(date(2026, 6, 30), ["INFY", "TCS", "RELIANCE"])

    members = get_nifty500_members_as_of(db, date(2026, 9, 18))

    assert members == ["INFY", "RELIANCE", "TCS"]  # sorted
    assert db.query.call_count == 2  # max(date), then symbols


def test_no_snapshot_returns_empty_rather_than_guessing():
    """Callers must fall back explicitly, not silently inherit today's index."""
    db = MagicMock()
    max_query = MagicMock()
    max_query.filter.return_value.scalar.return_value = None
    db.query.return_value = max_query

    assert get_nifty500_members_as_of(db, date(2020, 1, 1)) == []
    assert db.query.call_count == 1  # never queried for symbols


def test_duplicate_symbols_are_collapsed():
    db = _session(date(2026, 6, 30), ["INFY", "INFY", "TCS"])
    assert get_nifty500_members_as_of(db, date(2026, 9, 18)) == ["INFY", "TCS"]


def test_snapshot_is_pinned_by_equality_not_a_range():
    """The symbol query must pin ``as_of_date = <snapshot>``.

    Using ``<=`` here is exactly the union bug this helper exists to fix, so
    assert on the emitted SQL criteria rather than trusting the implementation.
    """
    db = MagicMock()
    max_query = MagicMock()
    max_query.filter.return_value.scalar.return_value = date(2026, 6, 30)
    symbol_query = MagicMock()
    symbol_query.filter.return_value.all.return_value = [("INFY",)]
    db.query.side_effect = [max_query, symbol_query]

    get_nifty500_members_as_of(db, date(2026, 9, 18))

    criteria = [str(c) for c in symbol_query.filter.call_args[0]]
    date_criterion = next(c for c in criteria if "as_of_date" in c)
    assert "<=" not in date_criterion
    assert "=" in date_criterion
    assert any("is_member" in c for c in criteria)

    # The max() lookup, by contrast, *should* use a range.
    assert "<=" in str(max_query.filter.call_args[0][0])
