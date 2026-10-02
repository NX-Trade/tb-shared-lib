"""Broker adapter interface and base types.

Concrete adapters (IBAdapter, ICICIAdapter) live in
services/tb-execution/broker/.  Only the abstract base types are
exported here so any service can reference the shared interface
without pulling in heavy broker dependencies (ib_async, breeze_connect).
"""

from tb_utils.broker.angelone_instruments import (
    AngelOneContract,
    build_angelone_lookup,
    fetch_angelone_scrip_master,
    resolve_angelone_contract,
    sync_angelone_instruments_to_redis,
)
from tb_utils.broker.base import (
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioHolding,
    PortfolioPosition,
    TimeInForce,
)
from tb_utils.broker.execution_db import (
    insert_order,
    update_order,
)
from tb_utils.broker.upstox_instruments import (
    build_upstox_lookup,
    fetch_and_parse_upstox_instruments,
    reset_upstox_circuit_breaker,
    resolve_upstox_instrument_key,
    sync_upstox_instruments_to_redis,
)

__all__ = [
    "AngelOneContract",
    "BrokerAdapter",
    "OrderRequest",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PortfolioHolding",
    "PortfolioPosition",
    "TimeInForce",
    "build_angelone_lookup",
    "build_upstox_lookup",
    "fetch_angelone_scrip_master",
    "fetch_and_parse_upstox_instruments",
    "insert_order",
    "resolve_angelone_contract",
    "reset_upstox_circuit_breaker",
    "resolve_upstox_instrument_key",
    "sync_angelone_instruments_to_redis",
    "sync_upstox_instruments_to_redis",
    "update_order",
]
