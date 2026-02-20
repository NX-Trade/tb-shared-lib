"""Config."""

import os


class NseApiConfig:
    """Configuration for NSE."""

    HEADERS = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/80.0.3987.149 Safari/537.36",
        "accept-language": "en,gu;q=0.9,hi;q=0.8",
        "accept-encoding": "gzip, deflate, br",
        "Content-Type": "application/json; charset=utf-8",
    }
    BASE_URL = "https://www.nseindia.com/"
    BASE_PATH = "https://www.nseindia.com/api/"
    QUOTE_DERIVATIVES = "quote-derivative?symbol={}"
    HISTORY_DERIVATIVES = "historical/fo/derivatives"
    EQUITY_QUOTE = "quote-equity?symbol={}"
    EQUITY_PATH = "{}"  # TO BE FILLED IN
    EVENT_CALENDAR_PATH = "event-calendar"
    FII_DII = "fiidiiTradeReact"

    # MARKET DATA
    NIFTY_EQUITIES_PATH = "equity-stockIndices?index=NIFTY%2050"
    MARKET_STATUS = "marketStatus"
    INDEXES = ["NIFTY", "BANKNIFTY"]

    # Not using currently
    INDEX_OC_PATH = "option-chain-indices?symbol={}"
    EQUITY_OC_PATH = "option-chain-equities?symbol={}"


class TbApiConfig:
    """Configuration for API."""

    BASE_URL = r"/api/v1"
    MSG_400 = "INVALID_PARAMETERS"
    MSG_401 = "UNAUTHORIZED_ACCESS"
    MSG_403 = "INVALID_PERMISSIONS"
    MSG_404 = "RECORD_NOT_FOUND"
    MSG_405 = "METHOD_NOT_ALLOWED"
    MSG_409 = "RECORD_ALREADY_EXISTS"
    MGS_501 = "METHOD_NOT_SUPPORTED"
    ERRORS = {
        "ClientBadRequest": {"message": MSG_400, "status": 400},
        "ClientNotAuthorized": {"message": MSG_401, "status": 401},
        "ClientNotPermitted": {"message": MSG_403, "status": 403},
        "ResourceAlreadyExists": {"message": MSG_409, "status": 409},
    }
    FINANCIAL_RESULTS = "financial results"
    INDEXES = ["NIFTY", "BANKNIFTY"]


class TbApiPathConfig:
    """Trading Bot Api Path Config."""

    headers = {"Content-Type": "application/json; charset=utf-8"}
    BASE_URI = os.getenv("ENVIRONMENT", "http://127.0.0.1:9000/api/v1/")
    EVENTS_PATH = "events"
    MAX_OI = "max_open_interest"
    EXPIRY_DATES = "expiry_dates"
    FII_DII = "fii_dii"
    ADV_DECLINE = "advance_decline"
    INDEX_DERIVATIVES = "index/derivatives/{}"
    EQUITY_DERIVATIVES = "equity/derivatives/{}"
    CUMULATIVE_DERIVATIVES = "cumulative/{}"
    HISTORICAL_DERIVATIVES = "historical/derivatives"
    INDEX = "index"
    EQUITY = "equity"
    EQUITY_META = "equity_meta"
    OPTION_META_DATA = "option_meta_data"
    TRADING_DATES = "trading_dates"
    ORDERS = "orders"
    POSITIONS = "positions"


class Config:
    """Configuration for App."""

    DEBUG = os.getenv("DEBUG", True)
    SECRET_KEY = os.getenv("SECRET_KEY", "my_precious_secret_key")
    CORS_HEADERS = "Content-Type"
