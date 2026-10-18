"""Writer and readers must derive the same token key, or orders use a stale one."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from tb_utils.queries.accounts import get_active_broker_account, resolve_broker_token_key
from tb_utils.redis.keys import get_broker_token_key, get_upstox_token_key


def db_returning(account):
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = account
    return db


def test_the_key_is_derived_from_the_account_not_the_stored_column():
    # token_storage_key says something else entirely; it must be ignored.
    account = SimpleNamespace(
        account_id=1, client_code="UPSTOX_PRIMARY", token_storage_key="upstox:access_token"
    )

    key = resolve_broker_token_key(db_returning(account), "UPSTOX")

    assert key == "broker:upstox:access_token:UPSTOX_PRIMARY"
    assert key != account.token_storage_key


def test_the_resolved_key_matches_what_the_collector_writes():
    """The one invariant that keeps the trade engine reading a live token."""
    account = SimpleNamespace(account_id=1, client_code="UPSTOX_PRIMARY")

    assert resolve_broker_token_key(db_returning(account), "UPSTOX") == get_broker_token_key(
        "UPSTOX", "UPSTOX_PRIMARY"
    )


def test_two_accounts_on_one_broker_get_different_keys():
    first = resolve_broker_token_key(
        db_returning(SimpleNamespace(account_id=1, client_code="UPSTOX_PRIMARY")), "UPSTOX"
    )
    second = resolve_broker_token_key(
        db_returning(SimpleNamespace(account_id=2, client_code="UPSTOX_SECOND")), "UPSTOX"
    )

    assert first != second


def test_no_active_account_falls_back_to_the_shared_key():
    assert resolve_broker_token_key(db_returning(None), "UPSTOX") == get_upstox_token_key()


def test_the_account_lookup_filters_to_the_broker_and_active_rows():
    account = SimpleNamespace(account_id=1, client_code="UPSTOX_PRIMARY")
    db = db_returning(account)

    assert get_active_broker_account(db, "upstox") is account
    # Lowest account_id wins, so the ordering must be applied.
    db.query.return_value.filter.return_value.order_by.assert_called_once()
