"""The credit-spread hedge-cost rule: off by default, a ceiling when the policy sets one."""

from tb_utils.options.spread_policy import SpreadPolicy
from tb_utils.options.spread_rules import check_hedge_cost


def test_the_rule_is_off_by_default_so_the_auto_trader_is_unchanged():
    assert check_hedge_cost(0.95, SpreadPolicy()) is None


def test_a_hedge_over_the_ceiling_is_refused_with_its_numbers():
    failed = check_hedge_cost(0.41, SpreadPolicy(max_credit_hedge_ratio=0.30))
    assert failed is not None and failed.code == "COSTLY_HEDGE"
    assert "41%" in failed.detail and "30%" in failed.detail


def test_a_hedge_at_or_under_the_ceiling_passes():
    policy = SpreadPolicy(max_credit_hedge_ratio=0.30)
    assert check_hedge_cost(0.30, policy) is None
    assert check_hedge_cost(0.12, policy) is None
