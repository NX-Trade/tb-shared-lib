import datetime
from enum import Enum


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
