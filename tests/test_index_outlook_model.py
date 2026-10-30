"""The index outlook table: what a row holds and what it defaults to."""

from tb_utils.models import IndexOutlook


def test_the_columns_that_make_an_outlook_readable_back_against_its_numbers():
    columns = set(IndexOutlook.__table__.columns.keys())
    assert {
        "symbol",
        "as_of",
        "mode",
        "evidence",
        "output",
        "model_name",
        "prompt_version",
        "degraded",
    } <= columns


def test_a_row_is_not_degraded_unless_said_so():
    column = IndexOutlook.__table__.c.degraded
    assert column.server_default.arg == "false" and column.nullable is False


def test_the_history_is_queryable_by_symbol_and_time():
    indexed = {c.name for c in IndexOutlook.__table__.columns if c.index}
    assert {"symbol", "as_of"} <= indexed
