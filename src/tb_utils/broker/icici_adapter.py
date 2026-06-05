"""ICICI Breeze broker adapter using breeze-connect.

Authentication uses a pre-generated session token (obtained by the operator
each morning from the ICICI Direct login flow and set as BREEZE_SESSION_TOKEN).
Session tokens expire daily, so this is a manual step before the 09:15 run.

Breeze uses product_type="cash" for equity delivery and "futures" for F&O.
Exchange codes: "NSE" for equities, "NFO" for F&O.
"""

import logging
import os

from breeze_connect import BreezeConnect

from tb_utils.broker.base import (
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioPosition,
)

logger = logging.getLogger(__name__)

_BREEZE_STATUS_MAP = {
    "Ordered": OrderStatus.PENDING,
    "Partial": OrderStatus.PARTIALLY_FILLED,
    "Executed": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "Rejected": OrderStatus.REJECTED,
    "Expired": OrderStatus.CANCELLED,
}

_SIDE_MAP = {
    OrderSide.BUY: "buy",
    OrderSide.SELL: "sell",
}

_ORDER_TYPE_MAP = {
    OrderType.LIMIT: "limit",
    OrderType.MARKET: "market",
}


class ICICIAdapter(BrokerAdapter):
    """Synchronous ICICI Breeze adapter for NSE cash equity orders."""

    def __init__(self):
        self._breeze: BreezeConnect | None = None
        self._connected = False

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self) -> bool:
        api_key = os.getenv("BREEZE_API_KEY", "")
        api_secret = os.getenv("BREEZE_API_SECRET", "")
        session_token = os.getenv("BREEZE_SESSION_TOKEN", "")
        if not api_key or not session_token:
            logger.error("BREEZE_API_KEY and BREEZE_SESSION_TOKEN must be set before connecting.")
            return False
        try:
            self._breeze = BreezeConnect(api_key=api_key)
            self._breeze.generate_session(
                api_secret=api_secret,
                session_token=session_token,
            )
            self._connected = True
            logger.info("Connected to ICICI Breeze.")
            return True
        except Exception as exc:
            logger.error("ICICI Breeze connection failed: %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._connected = False
        self._breeze = None
        logger.info("ICICI Breeze session cleared.")

    def is_connected(self) -> bool:
        return self._connected and self._breeze is not None

    def _assert_connected(self) -> None:
        if not self.is_connected():
            raise RuntimeError("ICICI Breeze adapter is not connected.")

    # ── Orders ─────────────────────────────────────────────────────────────

    def place_order(self, request: OrderRequest) -> OrderResult:
        self._assert_connected()
        try:
            params = {
                "stock_code": request.symbol,
                "exchange_code": "NSE",
                "product": "cash",
                "action": _SIDE_MAP[request.side],
                "order_type": _ORDER_TYPE_MAP[request.order_type],
                "quantity": str(request.quantity),
                "validity": "day",
                "stoploss": "0",
                "disclosed_quantity": "0",
                "transaction_type": _SIDE_MAP[request.side],
            }
            if request.order_type == OrderType.LIMIT:
                if request.limit_price is None:
                    raise ValueError("limit_price is required for LIMIT orders")
                params["price"] = str(request.limit_price)
            else:
                params["price"] = "0"

            response = self._breeze.place_order(**params)
            if response.get("Status") != 200:
                msg = response.get("Error", str(response))
                logger.error("Breeze place_order rejected: %s", msg)
                return OrderResult(broker_order_id="", status=OrderStatus.REJECTED, message=msg)

            order_id = response["Success"]["order_id"]
            logger.info(
                "Placed %s %s %d @ %s → Breeze order %s",
                request.side.value,
                request.symbol,
                request.quantity,
                request.limit_price or "MKT",
                order_id,
            )
            return OrderResult(broker_order_id=order_id, status=OrderStatus.PENDING)

        except Exception as exc:
            logger.error("place_order failed for %s: %s", request.symbol, exc)
            return OrderResult(broker_order_id="", status=OrderStatus.REJECTED, message=str(exc))

    def cancel_order(self, broker_order_id: str) -> bool:
        self._assert_connected()
        try:
            response = self._breeze.cancel_order(
                exchange_code="NSE",
                order_id=broker_order_id,
            )
            if response.get("Status") != 200:
                logger.warning("Breeze cancel_order failed: %s", response.get("Error"))
                return False
            logger.info("Cancelled Breeze order %s.", broker_order_id)
            return True
        except Exception as exc:
            logger.error("cancel_order failed for %s: %s", broker_order_id, exc)
            return False

    def get_order_status(self, broker_order_id: str) -> OrderResult:
        self._assert_connected()
        try:
            response = self._breeze.get_order_detail(
                exchange_code="NSE",
                order_id=broker_order_id,
            )
            if response.get("Status") != 200:
                return OrderResult(
                    broker_order_id=broker_order_id,
                    status=OrderStatus.CANCELLED,
                    message=response.get("Error", "Unknown"),
                )
            detail = response["Success"][0]
            status = _BREEZE_STATUS_MAP.get(detail.get("order_status", ""), OrderStatus.PENDING)
            filled_qty = int(detail.get("executed_quantity", 0))
            avg_price = float(detail.get("average_price", 0)) or None
            return OrderResult(
                broker_order_id=broker_order_id,
                status=status,
                filled_quantity=filled_qty,
                avg_fill_price=avg_price,
            )
        except Exception as exc:
            logger.error("get_order_status failed for %s: %s", broker_order_id, exc)
            return OrderResult(
                broker_order_id=broker_order_id,
                status=OrderStatus.PENDING,
                message=str(exc),
            )

    # ── Portfolio ──────────────────────────────────────────────────────────

    def get_positions(self) -> list[PortfolioPosition]:
        self._assert_connected()
        try:
            response = self._breeze.get_portfolio_positions()
            if response.get("Status") != 200:
                logger.warning("get_positions: Breeze returned non-200: %s", response)
                return []
            positions = []
            for item in response.get("Success") or []:
                qty = int(item.get("quantity", 0))
                if qty == 0:
                    continue
                positions.append(
                    PortfolioPosition(
                        symbol=item.get("stock_code", ""),
                        quantity=qty,
                        avg_price=float(item.get("average_price", 0)),
                        market_value=float(item.get("current_amount", 0)),
                        unrealized_pnl=float(item.get("unrealised_profit", 0)),
                    )
                )
            return positions
        except Exception as exc:
            logger.error("get_positions failed: %s", exc)
            return []

    def get_last_price(self, symbol: str) -> float | None:
        self._assert_connected()
        try:
            response = self._breeze.get_quotes(
                stock_code=symbol,
                exchange_code="NSE",
                product_type="cash",
                expiry_date="",
                right="",
                strike_price="",
            )
            if response.get("Status") != 200:
                return None
            ltp = response["Success"][0].get("ltp")
            return float(ltp) if ltp else None
        except Exception as exc:
            logger.error("get_last_price failed for %s: %s", symbol, exc)
            return None
