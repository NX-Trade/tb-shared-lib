"""The fresh-chain hand-off: the collector writes a snapshot, the trade path loads it or fails."""

import datetime as dt
import json

import pytest
from test_spread_engine import NOW, RELAXED, make_chain

from tb_utils.options import fresh_chain as fc
from tb_utils.options.spread_engine import FreshChain, StaleChainError, build_vertical_spread
from tb_utils.redis.keys import get_fresh_chain_key

REQUESTED = NOW
FETCHED = NOW + dt.timedelta(seconds=2)


class FakeRedis:
    """Just enough of a Redis client: get / setex with the TTL recorded."""

    def __init__(self):
        self.data, self.ttl = {}, {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, seconds, value):
        self.data[key], self.ttl[key] = value, seconds


def records_of(chain):
    return [
        fc.fresh_record(
            q.expiry, q.strike, q.option_type, q.bid, q.ask, q.ltp, q.open_interest, q.volume, q.iv
        )
        for q in chain.quotes
    ]


def stored(redis, symbol="TESTCO", spot=1000.0, records=None, fetched=FETCHED, requested=REQUESTED):
    chain = make_chain()
    rows = records if records is not None else records_of(chain)
    payload = fc.build_payload(symbol, spot, rows, requested, fetched)
    fc.store_fresh_chain(redis, symbol, payload)
    return chain


# ── Key and storage ──────────────────────────────────────────────────────────


def test_the_key_is_per_symbol_and_case_insensitive():
    key = get_fresh_chain_key("sail")
    assert key == get_fresh_chain_key("SAIL") == "market_data:fresh_chain:SAIL"


def test_the_snapshot_is_short_lived():
    redis = FakeRedis()
    stored(redis)
    assert redis.ttl[get_fresh_chain_key("TESTCO")] == fc.FRESH_CHAIN_TTL_SECONDS
    assert fc.FRESH_CHAIN_TTL_SECONDS <= 600  # a trade decision never reads an old one


def test_the_payload_states_when_it_was_asked_for_and_when_it_was_fetched():
    redis = FakeRedis()
    stored(redis)
    payload = json.loads(redis.data[get_fresh_chain_key("TESTCO")])
    assert payload["requested_at"] == REQUESTED.isoformat()
    assert payload["fetched_at"] == FETCHED.isoformat()
    assert payload["spot"] == 1000.0


def test_a_stored_payload_can_be_read_back_without_building_a_chain():
    redis = FakeRedis()
    stored(redis)
    payload = fc.read_payload(redis, "testco")
    assert payload["fetched_at"] == FETCHED.isoformat()
    assert fc.read_payload(FakeRedis(), "TESTCO") is None


# ── Loading ──────────────────────────────────────────────────────────────────


def test_a_fresh_payload_loads_as_a_fresh_chain():
    redis, original = FakeRedis(), None
    original = stored(redis)
    fresh = fc.load_fresh_chain(redis, "TESTCO", REQUESTED, lot_size=500)
    assert isinstance(fresh, FreshChain)
    assert fresh.chain.ts == FETCHED and fresh.requested_at == REQUESTED
    assert fresh.chain.spot == 1000.0 and fresh.chain.lot_size == 500
    assert len(fresh.chain.quotes) == len(original.quotes)
    a, b = original.quotes[0], fresh.chain.quotes[0]
    fields = ["expiry", "strike", "option_type", "bid", "ask", "iv"]
    assert [getattr(a, f) for f in fields] == [getattr(b, f) for f in fields]


def test_an_expiry_stored_as_a_datetime_is_read_as_its_date():
    """The collector wrote "2026-11-23T00:00:00": every STC spread on 30 Oct was skipped."""
    redis = FakeRedis()
    original = stored(redis)
    payload = fc.read_payload(redis, "TESTCO")
    for record in payload["records"]:
        record["e"] = record["e"] + "T00:00:00"
    fc.store_fresh_chain(redis, "TESTCO", payload)
    fresh = fc.load_fresh_chain(redis, "TESTCO", REQUESTED, lot_size=500)
    assert [q.expiry for q in fresh.chain.quotes] == [q.expiry for q in original.quotes]


def test_the_loaded_chain_drives_the_engine():
    redis = FakeRedis()
    stored(redis)
    fresh = fc.load_fresh_chain(redis, "TESTCO", REQUESTED, lot_size=500)
    result = build_vertical_spread(fresh, "BUY", NOW, RELAXED)
    assert result.skip is None, result.skip


def test_a_snapshot_fetched_after_the_request_is_accepted_even_if_asked_for_earlier():
    redis = FakeRedis()
    stored(redis)
    assert fc.load_fresh_chain(redis, "TESTCO", REQUESTED - dt.timedelta(minutes=1), 500)


def test_a_snapshot_older_than_this_request_is_refused():
    """Another signal's refresh may still be sitting there: it does not vouch for this decision."""
    redis = FakeRedis()
    stored(redis)
    with pytest.raises(StaleChainError):
        fc.load_fresh_chain(redis, "TESTCO", FETCHED + dt.timedelta(seconds=1), 500)


def test_a_snapshot_fetched_exactly_at_the_request_is_accepted():
    redis = FakeRedis()
    stored(redis)
    assert fc.load_fresh_chain(redis, "TESTCO", FETCHED, 500)


def test_no_snapshot_is_unavailable_not_stale():
    with pytest.raises(fc.ChainUnavailable, match="no fresh chain"):
        fc.load_fresh_chain(FakeRedis(), "TESTCO", REQUESTED, 500)


CORRUPT = [
    "not json",
    "[]",
    '{"spot": 1000}',
    json.dumps({"fetched_at": "x", "spot": 1000, "records": []}),
]


@pytest.mark.parametrize("raw", CORRUPT)
def test_a_corrupt_snapshot_is_unavailable(raw):
    redis = FakeRedis()
    redis.data[get_fresh_chain_key("TESTCO")] = raw
    with pytest.raises(fc.ChainUnavailable):
        fc.load_fresh_chain(redis, "TESTCO", REQUESTED, 500)


def test_a_snapshot_without_a_spot_or_without_quotes_is_unavailable():
    redis = FakeRedis()
    stored(redis, spot=0.0)
    with pytest.raises(fc.ChainUnavailable, match="spot"):
        fc.load_fresh_chain(redis, "TESTCO", REQUESTED, 500)
    redis = FakeRedis()
    stored(redis, records=[])
    with pytest.raises(fc.ChainUnavailable, match="no quotes"):
        fc.load_fresh_chain(redis, "TESTCO", REQUESTED, 500)


def test_missing_prices_become_none_not_zero():
    """A one-sided or unpriced quote must stay visibly missing so the liquidity rules reject it."""
    redis = FakeRedis()
    record = fc.fresh_record(dt.date(2026, 11, 26), 1000.0, "CE", None, 5.0, 0.0, 10, 20, 0.0)
    stored(redis, records=[record])
    quote = fc.load_fresh_chain(redis, "TESTCO", REQUESTED, 500).chain.quotes[0]
    assert quote.bid is None and quote.ask == 5.0
    assert quote.ltp is None and quote.iv is None


def test_the_tick_and_lot_size_come_from_the_caller_not_the_snapshot():
    redis = FakeRedis()
    stored(redis)
    chain = fc.load_fresh_chain(redis, "TESTCO", REQUESTED, lot_size=75, is_index=True).chain
    assert chain.lot_size == 75 and chain.is_index is True
