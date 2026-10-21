"""Tests for tb_utils.options.contracts — the exchange symbol an option order needs."""

import datetime as dt

import pytest

from tb_utils.options.contracts import (
    exchange_underlying,
    option_contract_symbol,
    parse_option_contract_symbol,
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
