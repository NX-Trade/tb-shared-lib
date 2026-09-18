"""Database execution helpers for order insertion, order updates, and position upserts.

Centralises DRY database mutations shared across tb-execution modules
(smart_open.py, monitor_positions.py).
"""

import datetime as dt
import logging

from sqlalchemy.orm import Session

from tb_utils.broker.base import OrderResult, OrderStatus
from tb_utils.models import Position, TradingOrder

logger = logging.getLogger(__name__)


def insert_order(
    session: Session,
    instrument_id: int,
    broker_id: int,
    side: str,
    order_type: str,
    quantity: int,
    limit_price: float | None,
    status: str,
    broker_order_id: str,
    strategy_id: str = "",
    stop_price: float | None = None,
    parent_order_id: int | None = None,
) -> TradingOrder:
    """Insert a new order into trading_order table.

    Args:
        session: Active SQLAlchemy session; the row is committed and refreshed.
        instrument_id: FK to ``instrument``.
        broker_id: FK to ``broker``.
        side: "BUY" or "SELL".
        order_type: Short DB code — "LMT", "MKT", "STP", "STP_LMT", …
        quantity: Order quantity in shares/lots.
        limit_price: Limit price, or None for market orders.
        status: Initial order status value (e.g. "PENDING").
        broker_order_id: Broker's id; empty string is stored as NULL.
        strategy_id: Tag identifying the originating strategy or exit reason.
        stop_price: Trigger price for stop orders.
        parent_order_id: The entry order this one protects. Set it for
            stop-loss / target legs so siblings can be found by foreign key
            instead of by parsing ``strategy_id`` strings — that is what makes
            OCO (cancel-the-other-leg-on-fill) possible.

    Returns:
        The persisted ``TradingOrder``.
    """
    order = TradingOrder(
        instrument_id=instrument_id,
        broker_id=broker_id,
        symbol="",
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        stop_price=stop_price,
        status=status,
        filled_quantity=0,
        broker_order_id=broker_order_id or None,
        strategy_id=strategy_id,
        parent_order_id=parent_order_id,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def update_order(session: Session, order: TradingOrder, result: OrderResult) -> None:
    """Update an existing TradingOrder row with broker fill result."""
    order.status = result.status.value
    order.filled_quantity = result.filled_quantity
    order.avg_fill_price = result.avg_fill_price
    order.broker_order_id = result.broker_order_id or order.broker_order_id
    if result.status == OrderStatus.FILLED:
        order.filled_at = dt.datetime.now(dt.UTC)
    session.commit()


def upsert_position(
    session: Session,
    instrument_id: int,
    broker_id: int,
    qty_delta: int,
    avg_price: float,
) -> None:
    """Upsert a position record in position table."""
    existing = (
        session.query(Position)
        .filter(
            Position.instrument_id == instrument_id,
            Position.broker_id == broker_id,
        )
        .first()
    )
    if existing:
        total_qty = existing.net_quantity + qty_delta
        if total_qty == 0:
            session.delete(existing)
        else:
            existing.average_price = round(
                (existing.average_price * existing.net_quantity + avg_price * qty_delta)
                / total_qty,
                2,
            )
            existing.net_quantity = total_qty
        session.commit()
    else:
        session.add(
            Position(
                instrument_id=instrument_id,
                broker_id=broker_id,
                net_quantity=qty_delta,
                average_price=avg_price,
            )
        )
        session.commit()
