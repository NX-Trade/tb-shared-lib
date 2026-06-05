"""IBKR broker adapter using ib-async 2.0.

Connects to a running TWS or IB Gateway instance on the configured host/port.
Paper trading uses port 7497; live trading uses 7496.

All order placements are synchronous from the caller's perspective — we await
ib_async's internal event loop and return only after the order is acknowledged
by the broker (or times out).
"""

import logging
import os
import threading

from ib_async import IB, Contract, LimitOrder, MarketOrder, Stock, Trade, util

from tb_utils.broker.base import (
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    OrderStatus,
    OrderType,
    PortfolioPosition,
)

logger = logging.getLogger(__name__)

# ib_async uses its own internal event loop; we run it in a dedicated thread
# so the rest of the execution service stays synchronous.
util.startLoop()

_IB_STATUS_MAP = {
    "Submitted": OrderStatus.PENDING,
    "PreSubmitted": OrderStatus.PENDING,
    "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "Inactive": OrderStatus.CANCELLED,
    "ApiCancelled": OrderStatus.CANCELLED,
}


class IBAdapter(BrokerAdapter):
    """Synchronous wrapper around ib-async 2.0 for NSE equities."""

    def __init__(self):
        self._ib = IB()
        self._lock = threading.Lock()

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self) -> bool:
        host = os.getenv("IB_HOST", "127.0.0.1")
        port = int(os.getenv("IB_PORT", "7497"))
        client_id = int(os.getenv("IB_CLIENT_ID", "1"))
        try:
            self._ib.connect(
                host=host,
                port=port,
                clientId=client_id,
                readonly=False,
            )
            logger.info(
                "Connected to IBKR at %s:%d (clientId=%d)",
                host,
                port,
                client_id,
            )
            return True
        except Exception as exc:
            logger.error("IBKR connection failed: %s", exc)
            return False

    def disconnect(self) -> None:
        if self._ib.isConnected():
            self._ib.disconnect()
            logger.info("Disconnected from IBKR.")

    def is_connected(self) -> bool:
        return self._ib.isConnected()

    # ── Contract helpers ───────────────────────────────────────────────────

    def _resolve_contract(self, symbol: str) -> Contract:
        exchange = os.getenv("IB_EXCHANGE", "NSE")
        currency = os.getenv("IB_CURRENCY", "INR")
        contract = Stock(symbol, exchange, currency)
        details = self._ib.reqContractDetails(contract)
        if not details:
            raise ValueError(f"Could not resolve IBKR contract for {symbol}")
        return details[0].contract

    # ── Orders ─────────────────────────────────────────────────────────────

    def place_order(self, request: OrderRequest) -> OrderResult:
        with self._lock:
            try:
                contract = self._resolve_contract(request.symbol)

                if request.order_type == OrderType.LIMIT:
                    if request.limit_price is None:
                        raise ValueError("limit_price is required for LIMIT orders")
                    ib_order = LimitOrder(
                        action=request.side.value,
                        totalQuantity=request.quantity,
                        lmtPrice=request.limit_price,
                    )
                else:
                    ib_order = MarketOrder(
                        action=request.side.value,
                        totalQuantity=request.quantity,
                    )

                trade: Trade = self._ib.placeOrder(contract, ib_order)
                self._ib.sleep(1)  # give TWS a moment to acknowledge

                broker_order_id = str(trade.order.orderId)
                status = _IB_STATUS_MAP.get(trade.orderStatus.status, OrderStatus.NEW)

                logger.info(
                    "Placed %s %s %d @ %s → IB order %s (%s)",
                    request.side.value,
                    request.symbol,
                    request.quantity,
                    request.limit_price or "MKT",
                    broker_order_id,
                    status.value,
                )
                return OrderResult(
                    broker_order_id=broker_order_id,
                    status=status,
                    filled_quantity=int(trade.orderStatus.filled),
                    avg_fill_price=trade.orderStatus.avgFillPrice or None,
                )
            except Exception as exc:
                logger.error("place_order failed for %s: %s", request.symbol, exc)
                return OrderResult(
                    broker_order_id="",
                    status=OrderStatus.REJECTED,
                    message=str(exc),
                )

    def cancel_order(self, broker_order_id: str) -> bool:
        with self._lock:
            try:
                open_trades = self._ib.openTrades()
                target = next(
                    (t for t in open_trades if str(t.order.orderId) == broker_order_id), None
                )
                if target is None:
                    logger.warning(
                        "cancel_order: order %s not found in open trades.", broker_order_id
                    )
                    return False
                self._ib.cancelOrder(target.order)
                self._ib.sleep(1)
                logger.info("Cancelled IB order %s.", broker_order_id)
                return True
            except Exception as exc:
                logger.error("cancel_order failed for %s: %s", broker_order_id, exc)
                return False

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        with self._lock:
            trades = self._ib.openTrades() + self._ib.trades()
            target = next((t for t in trades if str(t.order.orderId) == broker_order_id), None)
            if target is None:
                return OrderResult(
                    broker_order_id=broker_order_id,
                    status=OrderStatus.CANCELLED,
                    message="Order not found",
                )
            status = _IB_STATUS_MAP.get(target.orderStatus.status, OrderStatus.PENDING)
            return OrderResult(
                broker_order_id=broker_order_id,
                status=status,
                filled_quantity=int(target.orderStatus.filled),
                avg_fill_price=target.orderStatus.avgFillPrice or None,
            )

    # ── Portfolio ──────────────────────────────────────────────────────────

    def get_positions(self) -> list[PortfolioPosition]:
        with self._lock:
            positions = []
            for item in self._ib.portfolio():
                positions.append(
                    PortfolioPosition(
                        symbol=item.contract.symbol,
                        quantity=int(item.position),
                        avg_price=float(item.averageCost),
                        market_value=float(item.marketValue),
                        unrealized_pnl=float(item.unrealizedPNL),
                    )
                )
            return positions

    def get_last_price(self, symbol: str) -> float | None:
        with self._lock:
            try:
                contract = self._resolve_contract(symbol)
                ticker = self._ib.reqMktData(contract, "", False, False)
                self._ib.sleep(2)
                price = ticker.last or ticker.close
                self._ib.cancelMktData(contract)
                return float(price) if price else None
            except Exception as exc:
                logger.error("get_last_price failed for %s: %s", symbol, exc)
                return None
