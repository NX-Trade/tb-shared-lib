import datetime
from enum import Enum, IntEnum, StrEnum


class SourceEnum(IntEnum):
    NSE = 1
    IB = 2
    ICICI = 3
    SENSIBULL = 4
    # Upstox candles are adjusted for splits and bonuses, unlike NSE's raw
    # prices — RELIANCE closes 2655.70 then 1334.35 across its 2024 1:1 bonus
    # ex-date in the NSE series. Recording the source makes the price basis of
    # any row an explicit, queryable fact rather than an assumption.
    UPSTOX = 5


class BrokerTypeEnum(Enum):
    """Enum for BrokerType; to fetch data or post orders."""

    DATA = "DATA"
    OMS = "OMS"
    BOTH = "BOTH"


class MarketPositionEnum(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    LONG_UNWINDING = "LONG UNWINDING"
    SHORT_COVERING = "LONG COVERING"


class DerivativeTypeEnum(Enum):
    CALL = "CALL"
    CE = "CE"
    PUT = "PUT"
    PE = "PE"
    FUTURES = "FUTURES"


class MarketNamesEnum(Enum):
    CAPITAL_MARKET = "CAPITAL MARKET"
    CURRENCY = "CURRENCY"
    CURRENCY_FUTURE = "CURRENCYFUTURE"
    COMMODITY = "COMMODITY"
    DEBT = "DEBT"


class MarketStatusEnum(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class SecurityTypeEnum(Enum):
    EQUITY = "EQUITY"
    STOCK_FUTURES = "STOCK FUTURES"
    INDEX_FUTURES = "INDEX FUTURES"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"


class MarketTimingEnum(Enum):
    PRE_OPEN = datetime.time(9, 0)
    OPEN = datetime.time(9, 15)
    ONE_HOUR_CLOSE = datetime.time(10, 15)
    TWO_HOUR_CLOSE = datetime.time(11, 15)
    THREE_HOUR_CLOSE = datetime.time(12, 15)
    FOUR_HOUR_CLOSE = datetime.time(13, 15)
    FIVE_HOUR_CLOSE = datetime.time(14, 15)
    SIX_HOUR_CLOSE = datetime.time(15, 15)
    CLOSE = datetime.time(15, 30)


class DateFormatEnum(Enum):
    TB_DATE = "%d-%m-%Y"  # 21-01-2021
    NSE_DATE = "%d-%b-%Y"
    FULL_TS = "%d-%b-%Y %H:%M:%S"
    FULL_TS_TZ = "%Y-%m-%dT%H:%M:%S.%fZ"


class WeekDayEnum(Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class FiiDiiCategoryEnum(Enum):
    CASH = "CASH"
    INDEX_FUT = "INDEX FUT"
    INDEX_OPT = "INDEX OPT"
    STOCK_FUT = "STOCK FUT"
    STOCK_OPT = "STOCK OPT"
    MF_EQUITY = "MF EQUITY"
    MF_DEBT = "MF DEBT"
    FII_EQUITY = "FII EQUITY"
    FII_DEBT = "FII DEBT"
    PRO = "PRO"
    CLIENT = "CLIENT"


class TaskLogStatusEnum(IntEnum):
    PENDING = 0
    STARTED = 1
    SUCCESS = 2
    FAILED = 3
    RETRY = 4


class BrokerNameEnum(StrEnum):
    IB = "IB"
    ICICI = "ICICI"
    PAPER = "PAPER"
    UPSTOX = "UPSTOX"


class ExecutionModeEnum(StrEnum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class ExitReasonEnum(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    TARGET = "TARGET"
    TIME_BARRIER = "TIME_BARRIER"
    TRAILING_STOP = "TRAILING_STOP"
    BROKER_STOP_LOSS = "BROKER_STOP_LOSS"
    LIQUIDATION = "LIQUIDATION"
    MANUAL = "MANUAL"
    AUTO_SQUARE_OFF = "AUTO_SQUARE_OFF"


class SignalExecutionStatusEnum(StrEnum):
    """Why a trading_signal left the pending execution queue.

    Written by tb-execution to ``trading_signal.metadata["execution"]["status"]``
    and read by tb-backend / tb-ui, so a risk rejection or a skip is never
    mistaken for a real fill.
    """

    EXECUTED = "EXECUTED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
    SKIPPED_NO_SYMBOL = "SKIPPED_NO_SYMBOL"
    SKIPPED_NO_PRICE = "SKIPPED_NO_PRICE"
    SKIPPED_TIMEFRAME = "SKIPPED_TIMEFRAME"
    REJECTED_CORRELATION = "REJECTED_CORRELATION"
    REJECTED_SIZING = "REJECTED_SIZING"
    ERROR = "ERROR"


class ExecutionPlanStateEnum(StrEnum):
    """Lifecycle of an ``execution_plan`` row (tb-execution's entry state machine).

    ``LIMIT_ACTIVE`` → resting limit order being monitored until its deadline.
    ``TWAP_ACTIVE``  → limit cancelled, market slices being submitted one per tick.
    Terminal states are ``COMPLETED`` (fully or partially filled and booked),
    ``UNFILLED`` (nothing filled), ``FAILED`` and ``CANCELLED``.
    """

    LIMIT_ACTIVE = "LIMIT_ACTIVE"
    TWAP_ACTIVE = "TWAP_ACTIVE"
    COMPLETED = "COMPLETED"
    UNFILLED = "UNFILLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @classmethod
    def active(cls) -> tuple["ExecutionPlanStateEnum", ...]:
        """States the planner task still needs to advance."""
        return (cls.LIMIT_ACTIVE, cls.TWAP_ACTIVE)


class OrderIntentEnum(StrEnum):
    """What a trading_order does to the position book."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    STOP = "STOP"
    TARGET = "TARGET"
    SPREAD_LEG = "SPREAD_LEG"


class InstrumentTypeEnum(StrEnum):
    """Type of tradeable contract on a position, order, or trade row.

    Values match ``TradingSignal.instrument_type`` so that signals flow
    into execution plans and positions without a mapping step.
    """

    EQUITY = "EQUITY"
    FUT = "FUT"
    CE = "CE"
    PE = "PE"
