"""Abstract broker adapter interface.

Both IB and ICICI adapters implement this contract so the execution
engine never needs to know which broker it's talking to.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    LIMIT = "LMT"
    MARKET = "MKT"
    STOP = "STP"


class TimeInForce(StrEnum):
    DAY = "DAY"
    GTC = "GTC"


class OrderStatus(StrEnum):
    NEW = "NEW"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: float | None = None  # required for LIMIT orders
    stop_price: float | None = None  # required for STOP orders
    time_in_force: TimeInForce = TimeInForce.DAY
    strategy_id: str = ""
    product: str = "D"  # "D" = Delivery (CNC), "I" = Intraday (MIS)


@dataclass
class OrderResult:
    broker_order_id: str
    status: OrderStatus
    filled_quantity: int = 0
    avg_fill_price: float | None = None
    message: str = ""


@dataclass
class PortfolioPosition:
    symbol: str
    quantity: int
    avg_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    exit_price: Optional[float] = None
    # Quantity opened *and* closed within the session (an intraday round trip).
    # ``quantity`` is net, so a completed round trip reports 0 and the size of
    # the trade would otherwise be unrecoverable — which is how manually traded
    # intraday P&L went unrecorded. Adapters that cannot report it leave it 0.
    closed_quantity: int = 0


class BrokerAdapter(ABC):
    """All broker adapters must implement this interface."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the broker. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Cleanly close the broker connection."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the connection is live."""

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order. Returns an OrderResult with broker_order_id."""

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an open order. Returns True if cancelled successfully."""

    @abstractmethod
    def get_order_status(self, broker_order_id: str) -> OrderResult:
        """Fetch the current status of an order."""

    @abstractmethod
    def get_positions(self) -> list[PortfolioPosition]:
        """Return all current open positions."""

    @abstractmethod
    def get_last_price(self, symbol: str) -> float | None:
        """Fetch the last traded price for a symbol. Returns None on failure."""

    def place_gtt_order(
        self,
        request: OrderRequest,
        target_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        trailing_gap: Optional[float] = None,
    ) -> OrderResult:
        """Place a native multi-leg GTT / bracket order if supported by the broker."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support native GTT orders.")

    def modify_gtt_order(
        self,
        gtt_order_id: str,
        rules: list[dict],
        quantity: Optional[int] = None,
        order_type: str = "MULTIPLE",
    ) -> bool:
        """Modify an active GTT order if supported by the broker."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support modifying GTT orders."
        )

    def cancel_gtt_order(self, gtt_order_id: str) -> bool:
        """Cancel an active GTT order if supported by the broker."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support cancelling GTT orders."
        )

    def get_gtt_order_details(self, gtt_order_id: str) -> dict:
        """Retrieve details of an active or triggered GTT order."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support fetching GTT order details."
        )
