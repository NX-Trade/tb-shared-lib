"""Unit tests for ClientAccount model and schemas."""

from decimal import Decimal

from tb_utils import ClientAccount
from tb_utils.schema.account import ClientAccountCreate


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
