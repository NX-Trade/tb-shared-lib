# pylint: disable=redefined-outer-name
"""The research agent's vertical builder: now the spread engine's rules, on a stored chain.

It used to buy the at-the-money strike and sell near the signal's target, which priced its debit
spreads near 1:1, accepted reward:risk of 1.2 on an open interest of 300 and needed a target
(30 Oct 2026).
"""

import datetime as dt
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tb_utils.greeks import black_scholes_price
from tb_utils.models.historical_data import OptionChain
from tb_utils.options import strategy_builder as sb
from tb_utils.options.ideas import ChainData, Quote
from tb_utils.options.strategy_builder import BuiltOptionStrategy, build_vertical_spread_strategy
from tb_utils.time import IST

SPOT = 1000.0
LOT = 100
NOW = dt.datetime(2026, 10, 22, 19, 0, tzinfo=IST)
TS = NOW - dt.timedelta(hours=3)
EXPIRY = dt.date(2026, 11, 26)
STRIKES = [float(k) for k in range(800, 1201, 20)]


def _quote(strike, option_type, *, oi=20000, volume=50000, iv=25.0, half=0.05):
    days = (EXPIRY - NOW.date()).days
    mid = max(float(black_scholes_price(SPOT, strike, days, iv, option_type)), 0.5)
    return Quote(
        EXPIRY,
        strike,
        option_type,
        round(mid - half, 2),
        round(mid + half, 2),
        round(mid, 2),
        oi,
        volume,
        iv,
    )


def _chain(
    iv=35.0, **kwargs
):  # 35% puts the ATM straddle in the high regime: the engine sells credit
    quotes = [_quote(k, t, iv=iv, **kwargs) for k in STRIKES for t in ("CE", "PE")]
    return ChainData("ACME", TS, SPOT, LOT, False, quotes)


@pytest.fixture
def liquid(monkeypatch):
    monkeypatch.setattr(sb, "load_stored_chain", lambda db, symbol, lot_size: _chain())


def build(action="BUY", **kwargs):
    args = {
        "entry_price": SPOT,
        "target_price": 1060.0,
        "stop_loss": 950.0,
        "lot_size": LOT,
        "now": NOW,
    }
    args.update(kwargs)
    return build_vertical_spread_strategy(MagicMock(), "ACME", action, **args)


@pytest.mark.usefixtures("liquid")
def test_a_bullish_signal_builds_a_bull_vertical_that_meets_the_rules():
    strategy = build("BUY")
    assert isinstance(strategy, BuiltOptionStrategy)
    assert strategy.strategy_type in ("BULL_CALL_SPREAD", "BULL_PUT_SPREAD")
    if strategy.spread_type == "DEBIT":
        assert strategy.risk_reward_ratio >= 2.5 and strategy.net_premium > 0
    else:  # a credit spread keeps at least a quarter of its width
        width = abs(strategy.legs[0].strike_price - strategy.legs[1].strike_price)
        assert strategy.net_premium < 0 and -strategy.net_premium >= 0.25 * width - 1e-6


@pytest.mark.usefixtures("liquid")
def test_a_bearish_signal_builds_a_bear_vertical():
    strategy = build("SELL")
    assert strategy is not None
    assert strategy.strategy_type in ("BEAR_PUT_SPREAD", "BEAR_CALL_SPREAD")


@pytest.mark.usefixtures("liquid")
def test_the_bought_leg_is_sent_first_and_is_the_hedge():
    strategy = build("BUY")
    first, second = strategy.legs
    assert (first.execution_order, first.action, first.is_hedge) == (1, "BUY", True)
    assert (second.execution_order, second.action, second.is_hedge) == (2, "SELL", False)


@pytest.mark.usefixtures("liquid")
def test_no_target_is_needed():
    assert build("BUY", target_price=0.0) is not None


@pytest.mark.usefixtures("liquid")
def test_the_figures_are_per_share_and_consistent():
    strategy = build("BUY")
    width = abs(strategy.legs[0].strike_price - strategy.legs[1].strike_price)
    assert strategy.max_profit + strategy.max_loss == pytest.approx(width, abs=0.05)
    assert strategy.lot_size == LOT and strategy.margin_required_approx > 0


@pytest.mark.usefixtures("liquid")
def test_legs_are_priced_at_the_ask_and_the_bid_not_the_last_trade():
    strategy = build("BUY")
    chain = _chain()
    by_key = {(q.strike, q.option_type): q for q in chain.quotes}
    for leg in strategy.legs:
        quote = by_key[(leg.strike_price, leg.option_type)]
        assert leg.entry_premium == (quote.ask if leg.action == "BUY" else quote.bid)


def test_an_illiquid_chain_builds_nothing(monkeypatch):
    monkeypatch.setattr(sb, "load_stored_chain", lambda db, symbol, lot_size: _chain(volume=500))
    assert build("BUY") is None


def test_a_stale_chain_builds_nothing(monkeypatch):
    old = _chain()
    monkeypatch.setattr(
        sb,
        "load_stored_chain",
        lambda db, symbol, lot_size: ChainData(
            *(old.symbol, NOW - dt.timedelta(hours=40), old.spot, old.lot_size, False, old.quotes)
        ),
    )
    assert build("BUY") is None


def test_no_chain_builds_nothing(monkeypatch):
    monkeypatch.setattr(sb, "load_stored_chain", lambda db, symbol, lot_size: None)
    assert build("BUY") is None


@pytest.mark.parametrize(
    "kwargs", [{"entry_price": 0.0}, {"stop_loss": 0.0}, {"entry_price": -5.0}]
)
@pytest.mark.usefixtures("liquid")
def test_invalid_prices_build_nothing(kwargs):
    assert build("BUY", **kwargs) is None


@pytest.mark.usefixtures("liquid")
def test_the_old_one_to_one_is_gone():
    for action in ("BUY", "SELL"):
        strategy = build(action)
        if strategy is not None and strategy.spread_type == "DEBIT":
            assert strategy.risk_reward_ratio >= 2.5


# ── The stored chain loader ──────────────────────────────────────────────────


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    OptionChain.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


def _row(ts, strike, option_type="CE", **kw):
    values = {
        "ts": ts, "symbol": "ACME", "expiry_date": EXPIRY,
        "strike_price": strike, "option_type": option_type,
        "ltp": 10.0, "bid_price": 9.9, "ask_price": 10.1, "open_interest": 7000, "volume": 12000,
        "implied_vol": 25.0, "underlying_value": 1000.0, "source": "UPSTOX",
    }  # fmt: skip
    values.update(kw)
    return OptionChain(**values)


def test_the_loader_reads_only_the_latest_snapshot(session):
    older, newer = TS - dt.timedelta(hours=1), TS
    session.add_all([_row(older, 1000.0, ltp=5.0), _row(newer, 1000.0), _row(newer, 1020.0)])
    session.commit()
    chain = sb.load_stored_chain(session, "acme", LOT)
    assert chain.ts.replace(tzinfo=None) == newer.replace(tzinfo=None)
    assert sorted(q.strike for q in chain.quotes) == [1000.0, 1020.0]
    assert chain.spot == 1000.0 and chain.lot_size == LOT and chain.symbol == "ACME"


def test_the_loader_keeps_bid_ask_volume_and_treats_zero_as_unpriced(session):
    session.add_all(
        [_row(TS, 1000.0), _row(TS, 1020.0, bid_price=0, ask_price=0, ltp=0, implied_vol=0)]
    )
    session.commit()
    quotes = {q.strike: q for q in sb.load_stored_chain(session, "ACME", LOT).quotes}
    assert (quotes[1000.0].bid, quotes[1000.0].ask, quotes[1000.0].volume) == (9.9, 10.1, 12000)
    assert quotes[1020.0].bid is None and quotes[1020.0].ask is None and quotes[1020.0].iv is None


def test_the_loader_returns_none_for_an_unknown_symbol(session):
    assert sb.load_stored_chain(session, "NOPE", LOT) is None
