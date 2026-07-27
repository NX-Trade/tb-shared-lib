"""Broker adapter interface and base types.

Concrete adapters (IBAdapter, ICICIAdapter) live in
services/tb-execution/broker/.  Only the abstract base types are
exported here so any service can reference the shared interface
without pulling in heavy broker dependencies (ib_async, breeze_connect).
"""

from tb_utils.broker.base import (
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioPosition,
    TimeInForce,
)

__all__ = [
    "BrokerAdapter",
    "OrderRequest",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PortfolioPosition",
    "TimeInForce",
]
