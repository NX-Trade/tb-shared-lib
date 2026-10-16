"""Broker adapter interface and base types.

Concrete adapters (AngelOneAdapter, UpstoxAdapter, ICICIAdapter) live in
services/tb-trade-engine/broker/.  Only the abstract base types are
exported here so any service can reference the shared interface
without pulling in heavy broker dependencies.
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
from tb_utils.broker.icici_instruments import (
    ICICIContract,
    build_icici_cash_lookup,
    build_icici_derivative_lookup,
    fetch_icici_security_master,
    platform_symbol_for,
    resolve_icici_contract,
    sync_icici_instruments_to_redis,
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
    "ICICIContract",
    "OrderRequest",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PortfolioHolding",
    "PortfolioPosition",
    "TimeInForce",
    "build_angelone_lookup",
    "build_icici_cash_lookup",
    "build_icici_derivative_lookup",
    "build_upstox_lookup",
    "fetch_angelone_scrip_master",
    "fetch_and_parse_upstox_instruments",
    "fetch_icici_security_master",
    "platform_symbol_for",
    "insert_order",
    "resolve_angelone_contract",
    "resolve_icici_contract",
    "reset_upstox_circuit_breaker",
    "resolve_upstox_instrument_key",
    "sync_angelone_instruments_to_redis",
    "sync_icici_instruments_to_redis",
    "sync_upstox_instruments_to_redis",
    "update_order",
]
