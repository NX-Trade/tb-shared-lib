"""ICICI Direct (Breeze) instrument resolution.

Rows mirror the real columns of ICICI's NSEScripMaster.txt / FONSEScripMaster.txt
(downloaded 16 Oct 2026): RELIANCE is ``RELIND``, BANKNIFTY is ``CNXBAN``.
"""

import datetime as dt
import json
from dataclasses import asdict

import pytest

from tb_utils.broker import icici_instruments as mod
from tb_utils.broker.icici_instruments import (
    ICICIContract,
    build_icici_cash_lookup,
    build_icici_derivative_lookup,
    parse_derivative_symbol,
    platform_symbol_for,
    resolve_icici_contract,
    reverse_code_map,
)

TODAY = dt.date(2026, 10, 16)


class FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hlen(self, key):
        return len(self.hashes.get(key, {}))

    def expire(self, key, seconds):
        return True


def cash_row(short, nse, series="EQ", lot="1", token="1"):
    return {
        "Token": token,
        "ShortName": short,
        "Series": series,
        "Lotsize": lot,
        "ExchangeCode": nse,
    }


def fno_row(instrument, short, underlying, expiry, strike="0", option="XX", lot="500", token="9"):
    return {
        "Token": token,
        "InstrumentName": instrument,
        "ShortName": short,
        "ExpiryDate": expiry,
        "StrikePrice": strike,
        "OptionType": option,
        "LotSize": lot,
        "ExchangeCode": underlying,
    }


@pytest.fixture
def redis():
    r = FakeRedis()
    cash = build_icici_cash_lookup(
        [
            cash_row("RELIND", "RELIANCE"),
            cash_row("RELBE", "RELIANCE", series="BE"),
            cash_row("MAHMAH", "M&M"),
            cash_row("HDFWA2", "HDFCBANK", series="W3"),
            cash_row("HDFBAN", "HDFCBANK"),
        ]
    )
    derivatives, expiries = build_icici_derivative_lookup(
        [
            fno_row("FUTSTK", "RELIND", "RELIANCE", "27-Oct-2026"),
            fno_row("FUTSTK", "RELIND", "RELIANCE", "29-Dec-2026"),
            fno_row("OPTSTK", "RELIND", "RELIANCE", "27-Oct-2026", "1400", "CE"),
            fno_row("OPTSTK", "RELIND", "RELIANCE", "27-Oct-2026", "1400", "PE"),
            fno_row("OPTSTK", "ADAPOR", "ADANIPORTS", "29-Sep-2026", "1800", "CE", lot="300"),
            fno_row("OPTIDX", "NIFTY", "NIFTY 50", "27-Oct-2026", "25000", "CE", lot="65"),
            fno_row("OPTIDX", "NIFTY", "NIFTY 50", "20-Oct-2026", "25000", "CE", lot="65"),
            fno_row("OPTIDX", "CNXBAN", "NIFTY BANK", "27-Oct-2026", "55000.5", "PE", lot="30"),
            fno_row("FUTIDX", "CNXBAN", "NIFTY BANK", "27-Oct-2026", lot="30"),
        ]
    )
    r.hset(
        mod.REDIS_KEY_ICICI_INSTRUMENTS,
        {k: json.dumps(asdict(c)) for k, c in {**cash, **derivatives}.items()},
    )
    r.hset(mod.REDIS_KEY_ICICI_CODES, reverse_code_map(cash))
    r.hset(mod.REDIS_KEY_ICICI_EXPIRIES, {u: json.dumps(e) for u, e in expiries.items()})
    mod.clear_icici_cache()
    return r


def resolve(symbol, redis):
    return resolve_icici_contract(symbol, redis_client=redis, today=TODAY)


def test_cash_lookup_prefers_the_main_board_series():
    lookup = build_icici_cash_lookup(
        [cash_row("RELBE", "RELIANCE", series="BE"), cash_row("RELIND", "RELIANCE")]
    )
    assert lookup["RELIANCE"].stock_code == "RELIND"


def test_cash_lookup_skips_warrants_and_unlisted_series():
    lookup = build_icici_cash_lookup([cash_row("HDFWA2", "HDFCBANK", series="W3")])
    assert "HDFCBANK" not in lookup


def test_resolves_equity_by_nse_symbol_or_icici_code(redis):
    by_nse = resolve("RELIANCE", redis)
    assert (by_nse.exchange_code, by_nse.stock_code, by_nse.product_type) == (
        "NSE",
        "RELIND",
        "cash",
    )
    assert resolve("RELIND", redis) == by_nse
    assert resolve("RELIANCE-EQ", redis) == by_nse
    assert resolve("M&M", redis).stock_code == "MAHMAH"


@pytest.mark.parametrize(
    "symbol,code",
    [("NIFTY50", "NIFTY"), ("NIFTY 50", "NIFTY"), ("BANKNIFTY", "CNXBAN"), ("FINNIFTY", "NIFFIN")],
)
def test_resolves_index_spot_to_the_icici_index_code(redis, symbol, code):
    contract = resolve(symbol, redis)
    assert (contract.stock_code, contract.product_type, contract.exchange_code) == (
        code,
        "cash",
        "NSE",
    )


def test_resolves_an_option_written_as_underlying_year_month_strike(redis):
    contract = resolve("RELIANCE26OCT1400CE", redis)
    assert (contract.stock_code, contract.product_type, contract.right) == (
        "RELIND",
        "options",
        "call",
    )
    assert (contract.expiry_date, contract.strike_price, contract.lot_size) == (
        "2026-10-27",
        "1400",
        500,
    )
    assert contract.breeze_expiry == "2026-10-27T06:00:00.000Z"


def test_resolves_an_option_written_with_day_month_and_year(redis):
    contract = resolve("NIFTY27OCT2625000CE", redis)
    assert (contract.stock_code, contract.expiry_date, contract.strike_price) == (
        "NIFTY",
        "2026-10-27",
        "25000",
    )


def test_resolves_a_weekly_option_in_nse_compact_form(redis):
    contract = resolve("NIFTY26O2025000CE", redis)
    assert contract.expiry_date == "2026-10-20"


def test_resolves_the_label_form_without_a_year_to_the_next_such_expiry(redis):
    contract = resolve("RELIANCE 27OCT 1400 PE", redis)
    assert (contract.right, contract.expiry_date) == ("put", "2026-10-27")


def test_resolves_decimal_strikes_and_index_options(redis):
    contract = resolve("BANKNIFTY26OCT55000.5PE", redis)
    assert (contract.stock_code, contract.strike_price, contract.right) == (
        "CNXBAN",
        "55000.5",
        "put",
    )


def test_month_only_symbol_takes_the_months_last_expiry(redis):
    assert resolve("NIFTY26OCT25000CE", redis).expiry_date == "2026-10-27"


def test_resolves_futures(redis):
    contract = resolve("RELIANCE26DECFUT", redis)
    assert (contract.product_type, contract.expiry_date, contract.strike_price) == (
        "futures",
        "2026-12-29",
        "",
    )
    assert resolve("BANKNIFTY27OCT26FUT", redis).stock_code == "CNXBAN"


@pytest.mark.parametrize(
    "symbol",
    ["RELIANCE26OCT1500CE", "RELIANCE26NOV1400CE", "RELIANCE26OCT1400", "NOSUCH26OCT100CE", ""],
)
def test_refuses_to_guess_a_derivative_that_is_not_listed(redis, symbol):
    assert resolve(symbol, redis) is None


def test_ambiguous_text_is_settled_by_which_contract_exists(redis):
    # Read as day 26 / year 18 this is nonsense; read as year 26 / SEP it is the listed contract.
    contract = resolve("ADANIPORTS26SEP1800CE", redis)
    assert (contract.stock_code, contract.expiry_date, contract.lot_size) == (
        "ADAPOR",
        "2026-09-29",
        300,
    )


def test_parse_returns_every_reading():
    readings = parse_derivative_symbol("TATASTEEL29OCT185CE")
    shapes = {(r.year_month, r.day_month, r.expiry) for r in readings}
    assert ((2029, 10), None, None) in shapes
    assert (None, (10, 29), None) in shapes


def test_equity_falls_back_to_the_instrument_table():
    class Row:
        icici_stock_code = "ZZZ"

    class Query:
        def filter(self, *_):
            return self

        def first(self):
            return Row()

    class Db:
        def query(self, *_):
            return Query()

    mod.clear_icici_cache()
    contract = resolve_icici_contract("NEWCO", redis_client=None, db=Db(), today=TODAY)
    assert contract == ICICIContract(exchange_code="NSE", stock_code="ZZZ", product_type="cash")


def test_primes_an_empty_cache_from_the_security_master(monkeypatch):
    r = FakeRedis()
    mod.clear_icici_cache()
    monkeypatch.setattr(
        mod,
        "fetch_icici_security_master",
        lambda url=None: {mod.CASH_FILE: [cash_row("RELIND", "RELIANCE")], mod.FNO_FILE: []},
    )
    assert resolve("RELIANCE", r).stock_code == "RELIND"
    assert r.hlen(mod.REDIS_KEY_ICICI_INSTRUMENTS) > 0


def test_tick_size_comes_from_the_master_in_rupees():
    cash = build_icici_cash_lookup([{**cash_row("PENNY", "PENNY"), "ticksize": "0.01"}])
    assert cash["PENNY"].tick_size == 0.01
    contracts, _ = build_icici_derivative_lookup(
        [{**fno_row("FUTSTK", "RELIND", "RELIANCE", "27-Oct-2026"), "TickSize": "10"}]
    )
    assert contracts["RELIANCE|2026-10-27|FUT"].tick_size == 0.10


def test_reports_back_platform_symbols_for_positions_and_holdings(redis):
    assert platform_symbol_for("RELIND", redis) == "RELIANCE"
    assert platform_symbol_for("CNXBAN", redis) == "BANKNIFTY"
    assert platform_symbol_for("UNKNOWN", redis) == "UNKNOWN"


def test_a_reported_derivative_symbol_resolves_back_to_the_same_contract(redis):
    option = platform_symbol_for("RELIND", redis, dt.date(2026, 10, 27), 1400.0, "call", "options")
    assert option == "RELIANCE27OCT261400CE"
    assert resolve(option, redis).strike_price == "1400"
    future = platform_symbol_for("CNXBAN", redis, dt.date(2026, 10, 27), None, None, "futures")
    assert future == "BANKNIFTY27OCT26FUT"
    assert resolve(future, redis).product_type == "futures"
