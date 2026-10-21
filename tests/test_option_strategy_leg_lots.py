"""Leg quantity (`lots`): ratio structures like a 1x2x1 butterfly must be storable."""

import pytest
from pydantic import ValidationError

from tb_utils.models import OptionStrategyLeg
from tb_utils.options.strategy_builder import BuiltOptionLeg
from tb_utils.schema import OptionStrategyLegCreate


def _create(**overrides):
    base = {
        "execution_order": 1,
        "action": "BUY",
        "option_type": "CE",
        "strike_price": 1800.0,
        "symbol": "TECHM 28OCT 1800 CE",
        "entry_premium": 22.4,
    }
    return OptionStrategyLegCreate(**{**base, **overrides})


def test_schema_defaults_to_one_lot():
    assert _create().lots == 1


def test_schema_carries_ratio_lots():
    assert _create(action="SELL", lots=2).lots == 2


@pytest.mark.parametrize("bad", [0, -1])
def test_schema_rejects_non_positive_lots(bad):
    with pytest.raises(ValidationError):
        _create(lots=bad)


def test_model_column_is_non_null_with_server_default():
    col = OptionStrategyLeg.__table__.c.lots
    assert not col.nullable
    assert str(col.server_default.arg) == "1"


def test_built_leg_defaults_to_one_lot():
    leg = BuiltOptionLeg(
        execution_order=1,
        action="BUY",
        option_type="CE",
        strike_price=1800.0,
        symbol="X",
        entry_premium=1.0,
    )
    assert leg.lots == 1
