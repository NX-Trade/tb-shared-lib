"""Tests for tb_utils.options.contracts — the exchange symbol an option order needs."""

import datetime as dt

import pytest

from tb_utils.options.contracts import (
    compact_symbol_from_angel,
    exchange_underlying,
    option_contract_symbol,
    parse_angel_option_symbol,
    parse_option_contract_symbol,
    stored_underlying,
)

NOV3 = dt.date(2026, 11, 3)
NOV23 = dt.date(2026, 11, 23)


class TestBuild:
    def test_an_index_weekly_with_the_day_in_it(self):
        assert option_contract_symbol("NIFTY", NOV3, 22800, "CE") == "NIFTY26NOV0322800CE"

    def test_our_stored_index_name_becomes_the_exchange_name(self):
        assert option_contract_symbol("NIFTY50", NOV3, 22800, "PE") == "NIFTY26NOV0322800PE"
        assert (
            exchange_underlying("NIFTY50") == "NIFTY"
            and exchange_underlying("BANKNIFTY") == "BANKNIFTY"
        )

    def test_a_stock_monthly_is_spelled_the_same_way(self):
        assert option_contract_symbol("RELIANCE", NOV23, 1200, "CE") == "RELIANCE26NOV231200CE"

    def test_a_fractional_strike_keeps_its_decimal_and_a_whole_one_drops_it(self):
        assert option_contract_symbol("PNB", NOV23, 122.5, "PE") == "PNB26NOV23122.5PE"
        assert option_contract_symbol("PNB", NOV23, 122.0, "PE") == "PNB26NOV23122PE"

    @pytest.mark.parametrize("name", ["M&M", "BAJAJ-AUTO", "360ONE"])
    def test_names_with_symbols_or_digits_are_kept_as_the_exchange_has_them(self, name):
        assert option_contract_symbol(name, NOV23, 900, "CE").startswith(name)

    def test_lowercase_names_are_normalised(self):
        assert option_contract_symbol("reliance", NOV23, 1200, "CE") == "RELIANCE26NOV231200CE"

    @pytest.mark.parametrize("kind", ["XX", "FUT", ""])
    def test_rejects_anything_but_a_call_or_put(self, kind):
        with pytest.raises(ValueError):
            option_contract_symbol("NIFTY", NOV3, 22800, kind)

    @pytest.mark.parametrize("strike", [0, -5])
    def test_rejects_a_non_positive_strike(self, strike):
        with pytest.raises(ValueError):
            option_contract_symbol("NIFTY", NOV3, strike, "CE")


class TestParse:
    def test_reads_back_what_it_builds(self):
        for underlying, expiry, strike, kind in [
            ("NIFTY", NOV3, 22800.0, "CE"),
            ("PNB", NOV23, 122.5, "PE"),
            ("360ONE", NOV23, 900.0, "CE"),
            ("M&M", NOV23, 3200.0, "PE"),
            ("BAJAJ-AUTO", dt.date(2026, 12, 29), 9800.0, "CE"),
        ]:
            parts = parse_option_contract_symbol(
                option_contract_symbol(underlying, expiry, strike, kind)
            )
            assert (parts.underlying, parts.expiry, parts.strike, parts.option_type) == (
                underlying,
                expiry,
                strike,
                kind,
            )

    @pytest.mark.parametrize(
        "junk", ["", "NIFTY", "NIFTY 50", "RELIANCE", "NIFTY26XYZ0322800CE", "NIFTY26NOV3122800CE"]
    )
    def test_anything_that_is_not_a_contract_symbol_is_none(self, junk):
        assert parse_option_contract_symbol(junk) is None

    def test_an_impossible_date_is_none(self):
        assert parse_option_contract_symbol("NIFTY26FEB3022800CE") is None


def test_stored_underlying_reverses_the_exchange_name():
    assert stored_underlying("NIFTY") == "NIFTY50"
    assert stored_underlying("reliance") == "RELIANCE"


# ── Angel One's own spelling: NAME + DD + MON + YY + STRIKE + CE/PE ─────────────


@pytest.mark.parametrize(
    ("angel", "ours"),
    [
        ("TATASTEEL23NOV26150PE", "TATASTEEL26NOV23150PE"),
        ("CROMPTON23NOV26182.5CE", "CROMPTON26NOV23182.5CE"),  # fractional strike
        ("NAM-INDIA29DEC26820CE", "NAM-INDIA26DEC29820CE"),  # hyphen in the name
        ("M&M23NOV262500CE", "M&M26NOV232500CE"),  # ampersand in the name
        ("NIFTY29DEC2623000CE", "NIFTY26DEC2923000CE"),  # an index
        ("BANKNIFTY29DEC2646500PE", "BANKNIFTY26DEC2946500PE"),
        ("360ONE23NOV261000CE", "360ONE26NOV231000CE"),  # digits at the start of the name
    ],
)
def test_angels_spelling_becomes_ours(angel, ours):
    assert compact_symbol_from_angel(angel) == ours


def test_the_date_is_read_day_first_in_angels_spelling():
    parts = parse_angel_option_symbol("TATASTEEL23NOV26150PE")
    assert parts.expiry == dt.date(2026, 11, 23) and parts.strike == 150.0
    assert (parts.underlying, parts.option_type) == ("TATASTEEL", "PE")


NOT_OPTIONS = [
    "TATASTEEL-EQ",
    "RELIANCE",
    "TATASTEEL23NOV26FUT",
    "",
    "TATASTEEL23XYZ26150PE",  # not a month
    "TATASTEEL32NOV26150PE",  # not a day
]


@pytest.mark.parametrize("symbol", NOT_OPTIONS)
def test_anything_that_is_not_an_angel_option_is_none(symbol):
    assert compact_symbol_from_angel(symbol) is None


def test_the_round_trip_through_our_own_parser_recovers_the_contract():
    ours = compact_symbol_from_angel("CROMPTON23NOV26182.5CE")
    parts = parse_option_contract_symbol(ours)
    assert (parts.underlying, parts.expiry, parts.strike, parts.option_type) == (
        "CROMPTON",
        dt.date(2026, 11, 23),
        182.5,
        "CE",
    )
