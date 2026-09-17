"""Config."""

import os


class UpstoxApiConfig:
    """Upstox REST API v2 / v3 endpoint catalogue.

    All URL templates are defined here so the adapter never hard-codes a
    hostname.  Use ``UpstoxApiConfig.url(UpstoxApiConfig.ORDER_HISTORY)``
    or ``UpstoxApiConfig.v3_url(UpstoxApiConfig.GTT_PLACE)`` to build
    fully-qualified endpoints.

    Reference: https://upstox.com/developer/api-documentation/open-api
    """

    BASE_V2: str = "https://api.upstox.com/v2"
    BASE_V3: str = "https://api.upstox.com/v3"

    # ── v2 endpoints ─────────────────────────────────────────────────────
    USER_PROFILE: str = "/user/profile"
    ORDER_PLACE: str = "/order/place"
    ORDER_CANCEL: str = "/order/cancel"
    ORDER_HISTORY: str = "/order/history"
    PORTFOLIO_SHORT_TERM: str = "/portfolio/short-term-positions"
    PORTFOLIO_LONG_TERM: str = "/portfolio/long-term-holdings"
    MARKET_QUOTE_LTP: str = "/market-quote/ltp"

    # ── v3 endpoints ─────────────────────────────────────────────────────
    GTT_PLACE: str = "/order/gtt/place"
    GTT_MODIFY: str = "/order/gtt/modify"
    GTT_CANCEL: str = "/order/gtt/cancel"
    GTT_DETAIL: str = "/order/gtt"

    @classmethod
    def url(cls, path: str) -> str:
        """Return a fully-qualified v2 URL for the given path."""
        return f"{cls.BASE_V2}{path}"

    @classmethod
    def v3_url(cls, path: str) -> str:
        """Return a fully-qualified v3 URL for the given path."""
        return f"{cls.BASE_V3}{path}"

    @staticmethod
    def bearer_headers(access_token: str) -> dict:
        """Return standard Upstox request headers with Bearer auth."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }


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

    DEBUG = os.getenv("DEBUG", "1")
    SECRET_KEY = os.getenv("SECRET_KEY", "my_precious_secret_key")
    CORS_HEADERS = "Content-Type"
