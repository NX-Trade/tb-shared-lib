"""Resolving our option symbols to Angel One contracts, against real scrip-master rows.

The fixture is rows copied from Angel's public OpenAPIScripMaster.json on 2026-10-29. Angel spells
an
option ``NAME + DD + MON + YY + STRIKE + CE/PE`` (``TATASTEEL23NOV26150PE``) while we use
``UNDERLYING + YY + MON + DD + STRIKE + TYPE`` (``TATASTEEL26NOV23150PE``), and stores the strike
times 100 and the tick times 100, so a plain string lookup can never match.
"""

# pylint: disable=redefined-outer-name,unused-argument,protected-access
# (pytest fixtures are injected by name; the tests reset the module caches they exercise)

import datetime as dt
import json
from pathlib import Path

import pytest

from tb_utils.broker import angelone_instruments as ao
from tb_utils.options.contracts import option_contract_symbol

FIXTURE = Path(__file__).parent / "fixtures" / "angelone_scrip_master_sample.json"
ROWS = json.loads(FIXTURE.read_text(encoding="utf-8"))
NOV23 = dt.date(2026, 11, 23)
DEC29 = dt.date(2026, 12, 29)


class FakeRedisHash:
    """Hash commands only, with a counter so tests can see whether Redis was asked."""

    def __init__(self):
        self.hashes: dict[str, dict[str, str]] = {}
        self.reads = 0

    def hset(self, key, mapping=None):
        self.hashes.setdefault(key, {}).update(mapping or {})

    def hget(self, key, field):
        self.reads += 1
        return self.hashes.get(key, {}).get(field)

    def hlen(self, key):
        return len(self.hashes.get(key, {}))

    def expire(self, key, seconds):
        pass


@pytest.fixture(autouse=True)
def clean_caches():
    ao._IN_MEMORY_CONTRACT_CACHE.clear()
    ao.clear_option_index()
    yield
    ao._IN_MEMORY_CONTRACT_CACHE.clear()
    ao.clear_option_index()


@pytest.fixture
def indexed():
    ao.load_option_index(ao.build_angelone_option_index(ROWS))


def ours(underlying, expiry, strike, kind):
    return option_contract_symbol(underlying, expiry, strike, kind)


# ── Reading a row ────────────────────────────────────────────────────────────


def row(symbol):
    return next(r for r in ROWS if r["symbol"] == symbol)


def test_a_stock_option_row_becomes_a_contract_with_its_real_limits():
    contract = ao.contract_from_row(row("TATASTEEL23NOV26150PE"))
    assert (contract.exchange, contract.tradingsymbol, contract.symboltoken) == (
        "NFO",
        "TATASTEEL23NOV26150PE",
        "129547",
    )
    assert contract.lot_size == 2750 and contract.freeze_qty == 137501


def test_the_tick_is_stored_times_100_in_the_master():
    assert ao.contract_from_row(row("TATASTEEL23NOV26150PE")).tick_size == 0.01
    assert ao.contract_from_row(row("RELIANCE23NOV261080CE")).tick_size == 0.05


def test_a_contract_cached_before_these_fields_existed_still_loads():
    old = json.dumps({"exchange": "NSE", "tradingsymbol": "TCS-EQ", "symboltoken": "11536"})
    contract = ao.AngelOneContract(**json.loads(old))
    assert contract.lot_size == 0 and contract.tick_size == 0.0  # unknown, not made up


# ── The option index ─────────────────────────────────────────────────────────


def test_only_listed_options_are_indexed_not_futures_or_equities():
    index = ao.build_angelone_option_index(ROWS)
    assert len(index) == 9  # 11 rows less the equity and the future
    assert all(c.exchange == "NFO" and c.tradingsymbol[-2:] in ("CE", "PE") for c in index.values())


@pytest.mark.parametrize(
    ("name", "expiry", "strike", "kind", "key"),
    [
        ("TATASTEEL", NOV23, 150.0, "PE", "TATASTEEL|2026-11-23|150|PE"),
        ("CROMPTON", NOV23, 182.5, "CE", "CROMPTON|2026-11-23|182.5|CE"),
        ("NIFTY", DEC29, 23000.0, "CE", "NIFTY|2026-12-29|23000|CE"),
    ],
)
def test_the_key_spells_the_strike_in_rupees(name, expiry, strike, kind, key):
    assert ao.option_index_key(name, expiry, strike, kind) == key


def test_the_index_divides_the_strike_by_100():
    index = ao.build_angelone_option_index(ROWS)
    assert ao.option_index_key("TATASTEEL", NOV23, 150.0, "PE") in index
    assert ao.option_index_key("TATASTEEL", NOV23, 15000.0, "PE") not in index


# ── Resolving our symbols ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("underlying", "expiry", "strike", "kind", "angel_symbol", "token"),
    [
        ("TATASTEEL", NOV23, 150.0, "PE", "TATASTEEL23NOV26150PE", "129547"),
        ("CROMPTON", NOV23, 182.5, "CE", "CROMPTON23NOV26182.5CE", "100511"),  # fractional strike
        ("NAM-INDIA", DEC29, 820.0, "CE", "NAM-INDIA29DEC26820CE", None),  # hyphen in the name
        ("M&M", NOV23, 2500.0, "CE", "M&M23NOV262500CE", None),  # ampersand in the name
        ("NIFTY50", DEC29, 23000.0, "CE", "NIFTY29DEC2623000CE", None),  # our index name
        ("BANKNIFTY", DEC29, 46500.0, "PE", "BANKNIFTY29DEC2646500PE", None),
    ],
)
def test_our_compact_symbol_resolves_to_angels_contract(
    indexed, underlying, expiry, strike, kind, angel_symbol, token
):
    contract = ao.resolve_angelone_contract(ours(underlying, expiry, strike, kind))
    assert contract is not None, ours(underlying, expiry, strike, kind)
    assert contract.tradingsymbol == angel_symbol and contract.exchange == "NFO"
    if token:
        assert contract.symboltoken == token


def test_a_contract_that_is_not_listed_is_none_and_never_an_equity():
    """No guessing: an unlisted strike must not fall through to the underlying's cash contract."""
    assert ao.resolve_angelone_contract(ours("TATASTEEL", NOV23, 151.0, "PE")) is None
    assert ao.resolve_angelone_contract(ours("TATASTEEL", DEC29, 150.0, "PE")) is None


def test_angels_own_spelling_still_resolves_through_the_symbol_lookup(indexed):
    """``TATASTEEL23NOV26150PE`` also parses as a compact symbol (2023-11-26), which is not listed,
    so the resolver falls back to the exact symbol rather than failing."""
    ao._IN_MEMORY_CONTRACT_CACHE.update(ao.build_angelone_lookup(ROWS))
    contract = ao.resolve_angelone_contract("TATASTEEL23NOV26150PE")
    assert contract is not None and contract.symboltoken == "129547"


def test_the_compact_reading_wins_when_it_is_listed(indexed):
    """The engine only ever sends the compact form, so that reading is tried first."""
    symbol = ours("TATASTEEL", NOV23, 210.0, "CE")
    assert ao.resolve_angelone_contract(symbol).tradingsymbol == "TATASTEEL23NOV26210CE"


def test_a_bare_equity_symbol_is_unchanged(indexed):
    ao._IN_MEMORY_CONTRACT_CACHE.update(ao.build_angelone_lookup(ROWS))
    contract = ao.resolve_angelone_contract("TATASTEEL")
    assert contract is not None and contract.tradingsymbol == "TATASTEEL-EQ"


# ── Redis and the cache ──────────────────────────────────────────────────────


def test_syncing_writes_the_option_hash_and_fills_the_memory_index(monkeypatch):
    monkeypatch.setattr(ao, "fetch_angelone_scrip_master", lambda url=None: ROWS)
    redis = FakeRedisHash()
    ao.sync_angelone_instruments_to_redis(redis)
    assert redis.hlen(ao.REDIS_KEY_ANGELONE_OPTIONS) == 9
    assert ao.option_index_size() == 9


def test_a_fresh_process_resolves_from_redis_without_the_memory_index(monkeypatch):
    monkeypatch.setattr(ao, "fetch_angelone_scrip_master", lambda url=None: ROWS)
    redis = FakeRedisHash()
    ao.sync_angelone_instruments_to_redis(redis)
    ao.clear_option_index()  # a worker that has just started
    symbol = ours("TATASTEEL", NOV23, 150.0, "PE")
    contract = ao.resolve_angelone_contract(symbol, redis_client=redis)
    assert contract.symboltoken == "129547"
    assert redis.reads >= 1


def test_an_empty_redis_primes_itself_from_the_master_once(monkeypatch):
    calls = []
    monkeypatch.setattr(ao, "fetch_angelone_scrip_master", lambda url=None: calls.append(1) or ROWS)
    redis = FakeRedisHash()
    symbol = ours("TATASTEEL", NOV23, 150.0, "PE")
    contract = ao.resolve_angelone_contract(symbol, redis_client=redis)
    assert contract is not None and calls == [1]


def test_the_memory_index_is_reloaded_after_its_time_is_up(monkeypatch, indexed):
    """A long-lived worker must notice a newly listed series: the index expires and is re-read."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr(ao, "_monotonic", lambda: clock["now"])
    ao.load_option_index(ao.build_angelone_option_index(ROWS))
    assert not ao.option_index_expired()
    clock["now"] += ao.OPTION_INDEX_TTL_SECONDS + 1
    assert ao.option_index_expired()


def test_an_expired_index_is_refreshed_from_redis_on_the_next_lookup(monkeypatch):
    monkeypatch.setattr(ao, "fetch_angelone_scrip_master", lambda url=None: ROWS)
    redis = FakeRedisHash()
    ao.sync_angelone_instruments_to_redis(redis)
    clock = {"now": 0.0}
    monkeypatch.setattr(ao, "_monotonic", lambda: clock["now"])
    ao.load_option_index({})  # stale and empty
    clock["now"] += ao.OPTION_INDEX_TTL_SECONDS + 1
    assert ao.resolve_angelone_contract(ours("TATASTEEL", NOV23, 150.0, "PE"), redis_client=redis)
