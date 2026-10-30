"""Unit tests for ClientAccount model and schemas."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from tb_utils import ClientAccount
from tb_utils.models import FnoBanSync
from tb_utils.schema.account import ClientAccountCreate, ClientAccountUpdate


def test_client_account_model_instantiation():
    account = ClientAccount(
        client_code="UPSTOX_DEMO",
        client_name="Demo Client",
        broker_type="UPSTOX",
        allocated_capital=Decimal("150000.00"),
        max_risk_per_trade_pct=Decimal("0.0150"),
        max_active_trades=3,
        is_active=1,
        is_paper=False,
    )
    assert account.client_code == "UPSTOX_DEMO"
    assert account.broker_type == "UPSTOX"
    assert account.allocated_capital == Decimal("150000.00")
    assert "UPSTOX_DEMO" in repr(account)


def test_client_account_pydantic_schema():
    data = {
        "client_code": "ANGEL_TEST",
        "client_name": "Angel One Client",
        "broker_type": "ANGELONE",
        "allocated_capital": Decimal("200000.00"),
        "max_risk_per_trade_pct": Decimal("0.0100"),
        "max_active_trades": 2,
        "is_active": 1,
        "is_paper": False,
    }
    schema = ClientAccountCreate(**data)
    assert schema.client_code == "ANGEL_TEST"
    assert schema.broker_type == "ANGELONE"


SEGMENT_FLAGS = (
    "is_equity_trade_enabled",
    "is_derivative_trade_enabled",
    "is_commodity_trade_enabled",
)


def test_segment_flags_default_off_in_the_database_and_in_python():
    """No segment trades until an operator turns it on, whatever created the row."""
    columns = ClientAccount.__table__.c
    for flag in SEGMENT_FLAGS:
        assert not columns[flag].nullable, flag
        assert str(columns[flag].server_default.arg) == "false", flag
        assert columns[flag].default.arg is False, flag


def test_segment_flags_default_off_in_the_create_schema():
    schema = ClientAccountCreate(client_code="X", client_name="X", broker_type="ANGELONE")
    for flag in SEGMENT_FLAGS:
        assert getattr(schema, flag) is False, flag


def test_segment_flags_can_be_set_on_create_and_update():
    created = ClientAccountCreate(
        client_code="X", client_name="X", broker_type="ANGELONE", is_derivative_trade_enabled=True
    )
    assert created.is_derivative_trade_enabled is True
    assert created.is_equity_trade_enabled is False

    # An update that does not mention a flag must leave it alone (None = "not supplied").
    untouched = ClientAccountUpdate(client_name="Y")
    assert all(getattr(untouched, flag) is None for flag in SEGMENT_FLAGS)
    assert ClientAccountUpdate(is_equity_trade_enabled=False).is_equity_trade_enabled is False


def test_ban_sync_table_records_one_row_per_synced_day():
    columns = FnoBanSync.__table__.c
    assert [c.name for c in FnoBanSync.__table__.primary_key.columns] == ["trade_date"]
    assert not columns["synced_at"].nullable and not columns["banned_count"].nullable


def test_the_basket_limit_defaults_to_one_and_is_bounded():
    assert ClientAccount.__table__.c.max_open_option_baskets.server_default.arg == "1"
    assert (
        ClientAccountCreate(
            client_code="X", client_name="X", broker_type="ANGELONE"
        ).max_open_option_baskets
        == 1
    )
    assert (
        ClientAccountCreate(
            client_code="X", client_name="X", broker_type="ANGELONE", max_open_option_baskets=3
        ).max_open_option_baskets
        == 3
    )
    for bad in (0, 21):
        with pytest.raises(ValidationError):
            ClientAccountCreate(
                client_code="X",
                client_name="X",
                broker_type="ANGELONE",
                max_open_option_baskets=bad,
            )
    assert ClientAccountUpdate(client_name="Y").max_open_option_baskets is None
