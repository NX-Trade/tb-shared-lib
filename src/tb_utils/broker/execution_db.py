"""Database execution helpers for order insertion, order updates, and position upserts.

Centralises DRY database mutations shared across tb-execution modules
(smart_open.py, monitor_positions.py).
"""

import datetime as dt
import logging
from typing import Optional

from sqlalchemy.orm import Session

from tb_utils.broker.base import OrderResult, OrderStatus
from tb_utils.models import Instrument, Position, TradingOrder

logger = logging.getLogger(__name__)


# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
def insert_order(
    db: Session,
    instrument_id: int,
    broker_id: int,
    side: str,
    order_type: str,
    quantity: int,
    limit_price: Optional[float],
    status: str,
    broker_order_id: str,
    strategy_id: str = "",
    stop_price: Optional[float] = None,
    parent_order_id: Optional[int] = None,
    product: str = "D",
    symbol: str = "",
    trading_symbol: Optional[str] = None,
    instrument_type: Optional[str] = None,
    strike_price: Optional[float] = None,
    expiry_date: Optional[dt.date] = None,
) -> TradingOrder:
    """Insert a new order into trading_order table.

    Args:
        db: Active SQLAlchemy session; the row is committed and refreshed.
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
        product: "D" = Delivery (CNC), "I" = Intraday (MIS).
        symbol: Broker order symbol.
        trading_symbol: Derivative/trading symbol (takes precedence over symbol if provided).
        instrument_type: EQUITY, FUT, CE, PE.
        strike_price: Option strike price.
        expiry_date: Contract expiry date.

    Returns:
        The persisted ``TradingOrder``.
    """
    resolved_symbol = trading_symbol or symbol
    if not resolved_symbol and instrument_id:
        inst = db.get(Instrument, instrument_id)
        if inst:
            resolved_symbol = inst.symbol

    order = TradingOrder(
        instrument_id=instrument_id,
        broker_id=broker_id,
        symbol=resolved_symbol or "",
        instrument_type=instrument_type,
        strike_price=strike_price,
        expiry_date=expiry_date,
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
        product=product,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def update_order(db: Session, order: TradingOrder, result: OrderResult) -> None:
    """Update an existing TradingOrder row with broker fill result."""
    order.status = result.status.value
    order.filled_quantity = result.filled_quantity
    order.avg_fill_price = result.avg_fill_price
    order.broker_order_id = result.broker_order_id or order.broker_order_id
    if result.status == OrderStatus.FILLED:
        order.filled_at = dt.datetime.now(dt.UTC)
    db.commit()


# pylint: disable=too-many-arguments,too-many-positional-arguments
def upsert_position(
    db: Session,
    instrument_id: int,
    broker_id: int,
    qty_delta: int,
    avg_price: float,
    trading_symbol: Optional[str] = None,
    instrument_type: str = "EQUITY",
    strike_price: Optional[float] = None,
    expiry_date: Optional[dt.date] = None,
    is_algo: bool = True,
) -> None:
    """Upsert a position record in position table."""
    resolved_symbol = trading_symbol
    if not resolved_symbol and instrument_id:
        inst = db.get(Instrument, instrument_id)
        if inst:
            resolved_symbol = inst.symbol

    query = db.query(Position).filter(Position.broker_id == broker_id)
    if resolved_symbol:
        query = query.filter(Position.trading_symbol == resolved_symbol)
    else:
        query = query.filter(Position.instrument_id == instrument_id)

    existing = query.first()

    if existing:
        total_qty = existing.net_quantity + qty_delta
        if total_qty == 0:
            db.delete(existing)
        else:
            existing.average_price = round(
                (existing.average_price * existing.net_quantity + avg_price * qty_delta)
                / total_qty,
                2,
            )
            existing.net_quantity = total_qty
        db.commit()
    else:
        db.add(
            Position(
                instrument_id=instrument_id,
                broker_id=broker_id,
                trading_symbol=resolved_symbol or "",
                instrument_type=instrument_type,
                strike_price=strike_price,
                expiry_date=expiry_date,
                is_algo=is_algo,
                net_quantity=qty_delta,
                average_price=avg_price,
            )
        )
        db.commit()
