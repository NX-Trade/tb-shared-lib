"""The rules that run a saved option strategy: order, rollback, P&L, and when to exit.

Pure functions over plain dataclasses — no broker, no DB, no clock of their own — so every rule that
moves money can be tested exhaustively. The executor and the monitor in ``tb-trade-engine`` apply
them; they decide nothing themselves.

The rules, in the order they bite
---------------------------------
* **Entry: buy legs first, sell legs second.** The sold legs are only sent once every bought leg has
  filled, so a short is never naked and margin is reduced by the hedges already in place.
* **Rollback.** An entry that cannot complete is unwound: whatever filled is squared off at market,
  shorts (bought back) before longs (sold), so the unwind itself never leaves a naked short.
* **Exit: cover the sold legs first, then close the bought legs**, as market orders about a second
  apart.
* **Target: profit of ``multiple`` times the max loss.** Max loss comes from the prices actually
  filled, not the prices planned.
* **Expiry: square off on the last trading session before expiry**, from ``exit_time`` onward
  (and at once if that session has passed), so stock options are never left to physical settlement.

Money is rupees for the whole position; prices and strikes are per share.
"""

# stdlib
import datetime as dt
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Optional

# internal
from tb_utils.options.payoff import Leg, max_profit_loss, net_premium

BUY = "BUY"
SELL = "SELL"

# Execution statuses. ``OPEN`` is the only state in which the monitor watches for the target.
PENDING = "PENDING"
ENTERING = "ENTERING"
OPEN = "OPEN"
ROLLING_BACK = "ROLLING_BACK"
ROLLED_BACK = "ROLLED_BACK"
EXITING = "EXITING"
CLOSED = "CLOSED"
FAILED = "FAILED"
ACTIVE_STATUSES = (PENDING, ENTERING, OPEN, ROLLING_BACK, EXITING)

# Why an execution exited.
EXIT_TARGET = "TARGET"
EXIT_EXPIRY = "EXPIRY"
EXIT_MANUAL = "MANUAL"
EXIT_ENTRY_INCOMPLETE = "ENTRY_INCOMPLETE"

DEFAULT_PROFIT_TARGET_MULTIPLE = 2.0
# Options trade until the 15:30 close; 15:25 leaves five minutes for the exit to go out and fill.
EXPIRY_EXIT_TIME = dt.time(15, 25)
# Every order an option-strategy execution places carries this tag in ``trading_order.strategy_id``.
# The generic order worker, order reconciler and position reconciler leave tagged orders alone: they
# would book an option leg as an equity trade and apply equity exit rules to it.
ORDER_TAG_PREFIX = "optexec:"

# Brokers allowed to run option strategies live.
# * UPSTOX: verified with real orders.
# * ANGELONE: contract resolution is tested against Angel's real scrip master, and derivative
#   orders use the carry-forward product, a tag, lot and freeze checks, unknown-outcome handling
#   and a tag-based order lookup, all unit-tested. Four things can only be confirmed by the first
#   real order, as Angel has no sandbox: that ``ordertag`` is accepted, the quote response
#   layout, market orders on options, and the product name. Entries are still gated by
#   EXECUTION_MODE=LIVE, the live switch and the account's own flags.
# ICICI maps the product differently for options and is not verified.
SUPPORTED_OPTION_BROKERS = ("UPSTOX", "ANGELONE")

PRICE_TICK = 0.05
MARKETABLE_BUFFER = 0.02  # a marketable limit crosses the last price by this fraction


@dataclass(frozen=True)
class LegState:  # pylint: disable=too-many-instance-attributes
    """One leg of an execution as the rules see it."""

    leg_order: int
    action: str  # BUY | SELL
    option_type: str  # CE | PE
    strike: float
    expiry: dt.date
    lots: int
    quantity: int  # shares: lots * lot size
    entry_price: Optional[float] = None
    entry_filled: int = 0
    exit_price: Optional[float] = None
    exit_filled: int = 0
    mark: Optional[float] = None  # latest traded price

    @property
    def open_quantity(self) -> int:
        """Shares still held: entered and not yet closed."""
        return max(self.entry_filled - self.exit_filled, 0)

    @property
    def fully_entered(self) -> bool:
        return self.entry_filled >= self.quantity > 0


# ── Ordering ─────────────────────────────────────────────────────────────────


def unsupported_broker_reason(broker_type: str, is_paper: bool) -> Optional[str]:
    """Why a live account cannot run option strategies, or None. Paper accounts can always."""
    if is_paper or broker_type.upper() in SUPPORTED_OPTION_BROKERS:
        return None
    return f"option strategies are not supported on {broker_type} yet"


def order_tag(execution_id: int) -> str:
    """The ``strategy_id`` that marks an order as belonging to option execution ``execution_id``."""
    return f"{ORDER_TAG_PREFIX}{execution_id}"


def entry_sequence(legs: Sequence[LegState]) -> list[LegState]:
    """Bought legs first, then sold legs, each group in its own order."""
    return sorted(legs, key=lambda leg: (leg.action != BUY, leg.leg_order))


def exit_sequence(legs: Sequence[LegState]) -> list[LegState]:
    """Sold legs first (they are bought back), then bought legs (they are sold)."""
    return sorted(legs, key=lambda leg: (leg.action != SELL, leg.leg_order))


def closing_side(action: str) -> str:
    """The order side that closes a leg: a sold leg is bought back, a bought leg is sold."""
    return BUY if action == SELL else SELL


# ── Entry and rollback ───────────────────────────────────────────────────────


def entry_complete(legs: Sequence[LegState]) -> bool:
    """Every leg filled in full."""
    return bool(legs) and all(leg.fully_entered for leg in legs)


def legs_to_unwind(legs: Sequence[LegState]) -> list[LegState]:
    """What a rollback or an exit must close, in the safe order: only legs that hold shares."""
    return [leg for leg in exit_sequence(legs) if leg.open_quantity > 0]


def can_send_sell_legs(legs: Sequence[LegState]) -> bool:
    """The sold legs may go out only once every bought leg has filled in full."""
    buys = [leg for leg in legs if leg.action == BUY]
    return all(leg.fully_entered for leg in buys)


# ── P&L and the target ───────────────────────────────────────────────────────


def leg_pnl(leg: LegState) -> Optional[float]:
    """Open profit or loss of one leg at its mark; None until it has both a fill and a mark."""
    if leg.entry_price is None or leg.mark is None or leg.open_quantity == 0:
        return 0.0 if leg.open_quantity == 0 and leg.entry_filled > 0 else None
    sign = 1.0 if leg.action == BUY else -1.0
    return sign * (leg.mark - leg.entry_price) * leg.open_quantity


def open_pnl(legs: Sequence[LegState]) -> Optional[float]:
    """Total unrealised profit of what is still held; None if any held leg has no price yet.

    A partial answer would understate a loss or overstate a gain, so it is withheld instead.
    """
    total = 0.0
    for leg in legs:
        if leg.open_quantity == 0:
            continue
        pnl = leg_pnl(leg)
        if pnl is None:
            return None
        total += pnl
    return total


def realized_pnl(legs: Sequence[LegState]) -> float:
    """Profit or loss locked in by exits so far, on the shares that were closed."""
    total = 0.0
    for leg in legs:
        if leg.exit_price is None or leg.entry_price is None or leg.exit_filled == 0:
            continue
        closed = min(leg.exit_filled, leg.entry_filled)
        sign = 1.0 if leg.action == BUY else -1.0
        total += sign * (leg.exit_price - leg.entry_price) * closed
    return total


def payoff_legs(legs: Sequence[LegState], lot_size: int) -> list[Leg]:
    """The filled legs as ``payoff`` legs priced at what they actually filled at."""
    return [
        Leg(
            leg.action,
            leg.option_type,
            leg.strike,
            leg.entry_price or 0.0,
            leg.lots,
            lot_size,
            leg.expiry,
        )  # fmt: skip
        for leg in legs
        if leg.entry_price is not None and leg.fully_entered
    ]


def risk_from_fills(legs: Sequence[LegState], lot_size: int) -> tuple[float, float]:
    """``(max_loss, entry_net)`` in rupees from the prices actually filled.

    ``entry_net`` is the credit received (positive) or debit paid (negative). Raises ``ValueError``
    if the filled structure has an uncapped loss, which would mean an entry went wrong.
    """
    filled = payoff_legs(legs, lot_size)
    if not filled:
        raise ValueError("no filled legs to measure")
    loss = max_profit_loss(filled).max_loss.value
    if not math.isfinite(loss):
        raise ValueError("the filled structure has an uncapped loss")
    return -loss, net_premium(filled)


def profit_target(max_loss: float, multiple: float = DEFAULT_PROFIT_TARGET_MULTIPLE) -> float:
    """The profit, in rupees, at which the strategy exits: ``multiple`` times its max loss."""
    return max_loss * multiple


def target_reachable(max_profit: float, max_loss: float, multiple: float) -> bool:
    """Whether the best case can ever reach the target. Credit spreads and verticals cannot."""
    if max_loss <= 0:
        return False
    return max_profit >= max_loss * multiple


# ── Expiry ───────────────────────────────────────────────────────────────────


def last_session_before(expiry: dt.date, is_holiday: Callable[[dt.date], bool]) -> dt.date:
    """The last trading day strictly before ``expiry``."""
    day = expiry - dt.timedelta(days=1)
    while is_holiday(day):
        day -= dt.timedelta(days=1)
    return day


def expiry_exit_due(
    now: dt.datetime,
    expiry: dt.date,
    is_holiday: Callable[[dt.date], bool],
    exit_time: dt.time = EXPIRY_EXIT_TIME,
) -> bool:
    """True from ``exit_time`` on the last session before expiry, and at any time after it."""
    session = last_session_before(expiry, is_holiday)
    today = now.date()
    return today > session or (today == session and now.time() >= exit_time)


def exit_reason(
    pnl: Optional[float],
    target: Optional[float],
    now: dt.datetime,
    expiry: dt.date,
    is_holiday: Callable[[dt.date], bool],
) -> Optional[str]:
    """Why an open execution should be exited now, or None to keep holding.

    Expiry outranks the target: past the cut-off the position is closed whatever it earns.
    """
    if expiry_exit_due(now, expiry, is_holiday):
        return EXIT_EXPIRY
    if pnl is not None and target is not None and 0 < target <= pnl:
        return EXIT_TARGET
    return None


# ── Pricing ──────────────────────────────────────────────────────────────────


def marketable_limit(side: str, last_price: float, buffer: float = MARKETABLE_BUFFER) -> float:
    """A limit price that crosses the market: above the last price to buy, below it to sell.

    Rounded to the tick so the exchange accepts it, and never below one tick.
    """
    if last_price <= 0:
        raise ValueError("last_price must be positive")
    raw = last_price * (1 + buffer) if side == BUY else last_price * (1 - buffer)
    ticks = (
        math.ceil(raw / PRICE_TICK - 1e-9) if side == BUY else math.floor(raw / PRICE_TICK + 1e-9)
    )
    return round(max(ticks, 1) * PRICE_TICK, 2)
