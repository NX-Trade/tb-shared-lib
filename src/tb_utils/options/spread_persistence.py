"""Turn a :class:`Spread` into rows the existing option executor can run.

The engine decides *what* to trade; the executor (``tb-trade-engine``) already knows how to enter
it (buy legs before sell legs), roll back a partial entry and exit it. This module is the bridge: it
maps a spread onto ``OptionStrategySignal`` / ``OptionStrategyLeg`` and creates one pending
``OptionStrategyExecution`` per account. Money is rupees for the whole position, as the saved
strategies from the option builder are.

Exit parameters are decided here, at creation, and stored with the strategy so the monitor never
has to re-derive them: the profit target as a share of the maximum profit, and the stop as a loss
amount.
"""

import logging
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tb_utils.models import (
    OptionExecutionLeg,
    OptionStrategyExecution,
    OptionStrategyLeg,
    OptionStrategySignal,
)
from tb_utils.options import execution_rules as rules
from tb_utils.options.contracts import option_contract_symbol
from tb_utils.options.spread_types import CREDIT, Spread

logger = logging.getLogger("tb_utils.options.spread_persistence")

SOURCE_STC = "STC"
# Spec §7.1: take profit at 50-65 % of the maximum on a vertical; the middle of that range.
DEFAULT_CAPTURE_PCT = 0.575
# Spec §7.1: a credit spread stops at 1.5-2.0x the credit received.
DEFAULT_CREDIT_STOP_MULTIPLE = 1.75
MIN_TARGET_MULTIPLE = 0.01  # the column is Numeric(5, 2)


def profit_target_multiple(spread: Spread, capture_pct: float = DEFAULT_CAPTURE_PCT) -> float:
    """The executor's target (``max_loss x multiple``) that equals ``capture_pct`` of max profit."""
    multiple = capture_pct * spread.max_profit / spread.max_loss
    return max(round(multiple, 2), MIN_TARGET_MULTIPLE)


def stop_loss_amount(
    spread: Spread, credit_multiple: float = DEFAULT_CREDIT_STOP_MULTIPLE
) -> float:
    """The loss, in rupees, at which the position is closed.

    A debit spread stops at the whole debit (spec §7.1), which is its maximum loss. A credit spread
    stops at ``credit_multiple`` times the credit received, never beyond its maximum loss.
    """
    if spread.family != CREDIT:
        return spread.max_loss
    return round(min(spread.max_loss, credit_multiple * spread.net_premium), 2)


def _legs_of(spread: Spread) -> list[OptionStrategyLeg]:
    return [
        OptionStrategyLeg(
            execution_order=order,
            lots=leg.lots,
            action=leg.action,
            option_type=leg.option_type,
            strike_price=leg.strike,
            symbol=option_contract_symbol(
                spread.underlying, spread.expiry, leg.strike, leg.option_type
            ),
            entry_premium=leg.premium,
            delta=leg.delta,
            iv=leg.iv,
            open_interest=leg.open_interest,
            volume=leg.volume,
            is_hedge=leg.action == rules.BUY,
        )
        for order, leg in enumerate(spread.legs, start=1)  # bought legs are already first
    ]


def strategy_from_spread(  # pylint: disable=too-many-arguments
    spread: Spread,
    *,
    signal_id: Optional[int],
    entry_price: float,
    stop_loss: float,
    source: str = SOURCE_STC,
    capture_pct: float = DEFAULT_CAPTURE_PCT,
    metadata: Optional[dict[str, Any]] = None,
) -> OptionStrategySignal:
    """An unsaved strategy for ``spread``, linked to the signal that caused it."""
    structure = spread.structure.upper()
    meta: dict[str, Any] = dict(metadata or {})
    meta["engine"] = {
        "regime": spread.regime,
        "straddle_pct": spread.straddle_pct,
        "regime_straddle_pct": spread.regime_straddle_pct,
        "atm_iv": spread.atm_iv,
        "pop": spread.pop,
        "reward_risk": spread.reward_risk,
        "delta_miss": spread.delta_miss,
    }
    meta["exit"] = {"capture_pct": capture_pct, "stop_loss_amount": stop_loss_amount(spread)}
    return OptionStrategySignal(
        signal_id=signal_id,
        strategy_type=structure,
        spread_type=spread.family,
        underlying_symbol=spread.underlying,
        expiry_date=spread.expiry,
        dte=spread.dte,
        lot_size=spread.lot_size,
        net_premium=abs(spread.net_premium),
        max_profit=spread.max_profit,
        max_loss=spread.max_loss,
        risk_reward_ratio=spread.reward_risk,
        breakeven_price=spread.breakevens[0] if spread.breakevens else None,
        underlying_entry_price=entry_price,
        underlying_target_price=None,  # STC exits dynamically; it never carries a target
        underlying_stop_loss=stop_loss,
        status="ACTIVE",
        name=f"{spread.underlying} {structure.replace('_', ' ')} · {source}",
        source=source,
        profit_target_multiple=profit_target_multiple(spread, capture_pct),
        metadata_=meta,
        legs=_legs_of(spread),
    )


def new_execution(
    strategy: OptionStrategySignal, account_id: int, order_type: str
) -> OptionStrategyExecution:
    """One pending run of ``strategy`` on ``account_id``: a leg per strategy leg, in whole lots."""
    legs = sorted(strategy.legs, key=lambda x: (x.action != rules.BUY, x.execution_order))
    return OptionStrategyExecution(
        strategy_id=strategy.id,
        account_id=account_id,
        status=rules.PENDING,
        order_type=order_type,
        profit_target_multiple=strategy.profit_target_multiple,
        legs=[
            OptionExecutionLeg(
                leg_order=order,
                action=leg.action,
                option_type=leg.option_type,
                strike_price=leg.strike_price,
                expiry_date=strategy.expiry_date,
                lots=leg.lots,
                quantity=leg.lots * strategy.lot_size,
                broker_symbol=leg.symbol,
                status="PENDING",
            )
            for order, leg in enumerate(legs, start=1)
        ],
    )


def create_executions(
    db: Session, strategy: OptionStrategySignal, account_ids: list[int], order_type: str
) -> list[OptionStrategyExecution]:
    """Save the strategy once and queue one execution per account; returns the ones created.

    An account that already has this strategy active is skipped (the unique active index refuses
    it), never fatal: the other accounts still run. Nothing is saved when there are no accounts.
    """
    if not account_ids:
        return []
    db.add(strategy)
    db.commit()
    created: list[OptionStrategyExecution] = []
    for account_id in account_ids:
        execution = new_execution(strategy, account_id, order_type)
        db.add(execution)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.warning(
                "Strategy %s is already running on account %s; skipped.", strategy.id, account_id
            )
            continue
        created.append(execution)
    return created


__all__ = [
    "DEFAULT_CAPTURE_PCT",
    "DEFAULT_CREDIT_STOP_MULTIPLE",
    "SOURCE_STC",
    "create_executions",
    "new_execution",
    "profit_target_multiple",
    "stop_loss_amount",
    "strategy_from_spread",
]
