"""Trading Bot Utilities Library (tb_utils).

A comprehensive library for algorithmic trading with utilities for
PostgreSQL/TimescaleDB data handling, SQLAlchemy model management,
Pydantic schema validation, and external API integration.
"""

__version__ = "1.1.0"

from .config.database import DatabaseConfig, db_settings
from .config.db_session import SessionLocal, get_db

from .models import (
    Base,
    Broker,
    BrokerHealthLog,
    Candle,
    CorporateEvent,
    ExternalApiRequest,
    FiiDii,
    HistoricalEquityData,
    HistoricalIndexData,
    Instrument,
    MarketBreadth,
    News,
    OptionChain,
    Position,
    SystemLog,
    SystemMetric,
    Trade,
    TradingHoliday,
    TradingOrder,
    TradingSignal,
)
from .schema import (
    BrokerHealthLogResponse,
    BrokerResponse,
    CandleResponse,
    CorporateEventResponse,
    ExternalApiRequestCreate,
    ExternalApiRequestResponse,
    FiiDiiResponse,
    GenericResponseSchema,
    HistoricalEquityDataResponse,
    HistoricalIndexDataResponse,
    InstrumentResponse,
    MarketBreadthResponse,
    NewsResponse,
    OptionChainResponse,
    PositionResponse,
    SystemLogResponse,
    SystemMetricResponse,
    TradeResponse,
    TradingHolidayResponse,
    TradingOrderCreate,
    TradingOrderResponse,
    TradingSignalCreate,
    TradingSignalResponse,
)
from .request_maker import CircuitBreakerError, RequestMaker

__all__ = [
    # Version
    "__version__",
    # Config
    "DatabaseConfig",
    "db_settings",
    "SessionLocal",
    "get_db",
    # Models
    "Base",
    "Broker",
    "BrokerHealthLog",
    "Candle",
    "CorporateEvent",
    "ExternalApiRequest",
    "FiiDii",
    "HistoricalEquityData",
    "HistoricalIndexData",
    "Instrument",
    "MarketBreadth",
    "News",
    "OptionChain",
    "Position",
    "SystemLog",
    "SystemMetric",
    "Trade",
    "TradingHoliday",
    "TradingOrder",
    "TradingSignal",
    # Schemas
    "GenericResponseSchema",
    "BrokerResponse",
    "BrokerHealthLogResponse",
    "ExternalApiRequestCreate",
    "ExternalApiRequestResponse",
    "CorporateEventResponse",
    "TradingHolidayResponse",
    "HistoricalEquityDataResponse",
    "HistoricalIndexDataResponse",
    "CandleResponse",
    "OptionChainResponse",
    "InstrumentResponse",
    "FiiDiiResponse",
    "MarketBreadthResponse",
    "NewsResponse",
    "SystemMetricResponse",
    "SystemLogResponse",
    "TradingSignalCreate",
    "TradingSignalResponse",
    "TradingOrderCreate",
    "TradingOrderResponse",
    "PositionResponse",
    "TradeResponse",
    # Request Maker
    "RequestMaker",
    "CircuitBreakerError",
]
