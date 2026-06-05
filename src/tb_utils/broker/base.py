"""Abstract broker adapter interface.

Both IB and ICICI adapters implement this contract so the execution
engine never needs to know which broker it's talking to.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    LIMIT = "LMT"
    MARKET = "MKT"


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
    strategy_id: str = ""


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
