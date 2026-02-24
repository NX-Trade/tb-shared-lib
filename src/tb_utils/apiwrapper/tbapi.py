"""Trading Bot Internal API Wrapper.

Provides a layered HTTP client for the internal TradingBot API and
generic external REST API interactions.
"""
import functools
import json
import time
from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List, Optional, Union

import requests
from pydantic import BaseModel
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError, ReadTimeout, RequestException
from urllib3.exceptions import ReadTimeoutError

from .. import errors
from ..config.apiconfig import TbApiPathConfig
from ..utils.dtu import TODAY

logger = getLogger("tb-utils.apiwrapper.tbapi")


def request_decorator(func):
    """Decorator that handles standard HTTP exceptions and returns parsed JSON."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        resp = None
        try:
            resp = func(*args, **kwargs)
            resp.raise_for_status()
        except HTTPError as ex:
            logger.exception("HTTP error: %s", ex, exc_info=True)
        except (ReadTimeout, ReadTimeoutError) as ex:
            logger.exception("Timeout error: %s", ex, exc_info=True)
        except RequestsConnectionError as ex:
            logger.exception("Connection error: %s", ex, exc_info=True)
        except RequestException as ex:
            logger.exception("Request error: %s", ex, exc_info=True)
            raise SystemExit from ex
        except Exception as ex:
            logger.exception("Unknown Api error: %s", ex, exc_info=True)
            raise

        return resp.json() if resp else {}

    return wrapper


class ApiClient:
    """Base API client for making HTTP requests with retry logic."""

    def __init__(self, base_url: str, verify_ssl: Optional[bool] = None):
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.headers = {}

    def set_headers(self, headers: Dict[str, str]) -> None:
        """Set headers for all subsequent requests."""
        self.headers = headers

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Union[List, Dict[str, Any], BaseModel]] = None,
        retry_codes: Optional[List[int]] = None,
        max_retries: int = 3,
        retry_wait: int = 2,
    ) -> requests.Response:
        """Make an HTTP request with exponential backoff retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path or full URL
            params: Query parameters
            data: Request body data (dict, list, or Pydantic model)
            retry_codes: HTTP codes that trigger a retry (default: 429, 5xx)
            max_retries: Maximum retry attempts
            retry_wait: Seconds to wait between retries

        Returns:
            requests.Response

        Raises:
            TradingBotAPIException: After all retries exhausted
        """
        if retry_codes is None:
            retry_codes = [429, 500, 502, 503, 504]

        url = (
            endpoint
            if endpoint.startswith("http")
            else f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        )

        # Convert Pydantic models to dicts
        if isinstance(data, BaseModel):
            data = data.model_dump()

        kwargs: Dict[str, Any] = {
            "params": params,
            "headers": self.headers,
            "verify": self.verify_ssl,
        }

        if method.lower() in ["post", "put", "patch"] and data is not None:
            kwargs["json"] = data

        for attempt in range(max_retries):
            try:
                response = requests.request(method, url, **kwargs)

                if (
                    response.status_code < 400
                    or response.status_code not in retry_codes
                ):
                    return response

                logger.warning(
                    "Request failed with status %s. Attempt %s of %s",
                    response.status_code,
                    attempt + 1,
                    max_retries,
                )

                if attempt == max_retries - 1:
                    return response

                time.sleep(retry_wait)

            except (requests.RequestException, IOError) as e:
                if attempt == max_retries - 1:
                    raise

                logger.warning(
                    "Request exception: %s. Attempt %s of %s",
                    str(e),
                    attempt + 1,
                    max_retries,
                )
                time.sleep(retry_wait)

        raise errors.TradingBotAPIException("Maximum retries exceeded")

    def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Union[List, Dict[str, Any], BaseModel]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a request and parse JSON response."""
        try:
            response = self._make_request(
                method=method, endpoint=endpoint, data=data, params=params
            )
            return response.json() if response.content else {}
        except Exception as e:
            logger.error("API request error: %s", e, exc_info=True)
            if isinstance(e, ValueError):
                raise errors.TradingBotAPIException(str(e))
            raise

    def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a GET request."""
        return self.request("get", endpoint, params=params)

    def post(self, endpoint: str, data: Union[List, Dict[str, Any]]) -> Dict[str, Any]:
        """Make a POST request."""
        return self.request("post", endpoint, data=data)

    def put(self, endpoint: str, data: Union[List, Dict[str, Any]]) -> Dict[str, Any]:
        """Make a PUT request."""
        return self.request("put", endpoint, data=data)

    def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make a DELETE request."""
        return self.request("delete", endpoint)


class TbApiCore(ApiClient):
    """Core Trading Bot internal API wrapper.

    Handles auth headers and low-level CRUD endpoint methods.
    """

    def __init__(
        self, base_url: Optional[str] = None, verify_ssl: Optional[bool] = None
    ):
        super().__init__(base_url or TbApiPathConfig.BASE_URI, verify_ssl)
        self.x_force_delete = False
        self._make_tb_api_headers()

    def _make_tb_api_headers(self) -> None:
        headers = TbApiPathConfig.headers.copy()
        if self.x_force_delete:
            headers["X-Force-Delete"] = "true"
        self.set_headers(headers)

    def set_force_delete(self, force_delete: bool = True) -> None:
        """Enable or disable forced delete header."""
        self.x_force_delete = force_delete
        self._make_tb_api_headers()

    @request_decorator
    def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Union[List, Dict[str, Any]]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a request to the TradingBot internal API."""
        try:
            response = super()._make_request(
                method=method, endpoint=endpoint, data=data, params=params
            )
            return response.json() if response.content else {}
        except Exception as e:
            logger.error("API request error: %s", e, exc_info=True)
            if isinstance(e, ValueError):
                raise errors.TradingBotAPIException(str(e))
            raise

    def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self.request("get", endpoint, params=params)

    def post(self, endpoint: str, data: Union[List, Dict[str, Any]]) -> Dict[str, Any]:
        return self.request("post", endpoint, data=data)

    def put(self, endpoint: str, data: Union[List, Dict[str, Any]]) -> Dict[str, Any]:
        """PUT one item or iterate and PUT a list."""
        try:
            if isinstance(data, dict):
                return self.request("put", endpoint, data=data)

            if isinstance(data, list):
                results: Dict[str, Any] = {}
                for item in data:
                    result = self.request("put", endpoint, data=item)
                    results.update(result)
                return results

            return {}
        except errors.TradingBotAPIException as e:
            logger.warning("PUT request failed: %s", e, exc_info=True)
            return {}

    def delete(self, endpoint: str) -> Dict[str, Any]:
        self.set_force_delete(True)
        return self.request("delete", endpoint)

    # ---------- Domain Endpoints ----------

    def get_equity(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch equity data."""
        return self.get(f"{TbApiPathConfig.EQUITY}/{on_date}")

    def get_historical_derivatives(
        self, security: Optional[str] = None, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get historical derivatives data."""
        endpoint = TbApiPathConfig.HISTORICAL_DERIVATIVES
        if security:
            endpoint = f"{endpoint}/{security}"
        return self.get(endpoint, params=params)

    def get_fii_dii(self) -> Dict[str, Any]:
        """Fetch FII-DII investment data."""
        return self.get(TbApiPathConfig.FII_DII)

    def get_trading_dates_data(self) -> Dict[str, Any]:
        """Fetch all trading dates."""
        return self.get(TbApiPathConfig.TRADING_DATES)

    def get_orders_data(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch orders for a given date."""
        return self.get(f"{TbApiPathConfig.ORDERS}/{on_date}")

    def get_positions_data(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch positions for a given date."""
        return self.get(f"{TbApiPathConfig.POSITIONS}/{on_date}")

    def get_expiry_dates_data(self, security_type: str = "EQUITY") -> List[str]:
        """Fetch expiry dates for a security type."""
        return self.get(f"{TbApiPathConfig.EXPIRY_DATES}/{security_type.lower()}")

    def get_events_data(
        self,
        params: Optional[Dict[str, Any]] = None,
        securities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch event calendar data."""
        params = params or {}
        if securities:
            if len(securities) < 80:
                params["security__in"] = json.dumps(securities)
            else:
                logger.warning("Security list exceeds the safe API limit of 80.")
        return self.get(TbApiPathConfig.EVENTS_PATH, params=params)

    def create_orders(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POST new orders."""
        return self.post(f"{TbApiPathConfig.ORDERS}/{TODAY}", data=orders_data)

    def create_positions(self, positions_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POST new positions."""
        return self.post(f"{TbApiPathConfig.POSITIONS}/{TODAY}", data=positions_data)

    def update_orders_data(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """PUT updated orders."""
        return self.put(f"{TbApiPathConfig.ORDERS}/{TODAY}", data=orders_data)

    def update_positions_data(
        self, positions_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """PUT updated positions."""
        return self.put(f"{TbApiPathConfig.POSITIONS}/{TODAY}", data=positions_data)


class TbApiService:
    """Service layer with higher-level business operations built on TbApiCore."""

    def __init__(self, api_client: Optional[TbApiCore] = None):
        self.api = api_client or TbApiCore()

    def get_security_in_focus(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch securities in focus for a given date."""
        return self.api.get_equity(on_date)

    def get_investment(self) -> Dict[str, Any]:
        """Fetch FII-DII investment data."""
        return self.api.get_fii_dii()

    def get_trading_dates(self) -> Dict[str, Any]:
        """Fetch all trading dates."""
        return self.api.get_trading_dates_data()

    def get_orders(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch orders for a given date."""
        return self.api.get_orders_data(on_date)

    def get_positions(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch positions for a given date."""
        return self.api.get_positions_data(on_date)

    def get_expiry_dates(self, security_type: str = "EQUITY") -> List[str]:
        """Fetch expiry dates for a security type."""
        return self.api.get_expiry_dates_data(security_type)

    def get_events(
        self,
        query: Optional[Dict[str, Any]] = None,
        securities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch event calendar with optional security filter."""
        return self.api.get_events_data(query, securities)

    def save_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Persist new orders to the API, skipping existing ones by orderId.

        Args:
            orders: Raw order dicts from IB broker.

        Returns:
            API creation response
        """
        cache_orders = self.api.get_orders_data()
        cache_order_ids = {od.get("orderId") for od in cache_orders if "orderId" in od}

        new_orders = [
            {
                **order,
                "security": order.get("symbol", ""),
                "limit_price": order.get("lmtPrice", 0),
                "on_date": datetime.today().isoformat(),
                "timestamp": datetime.now().isoformat(),
            }
            for order in orders
            if order.get("orderId") not in cache_order_ids
        ]

        if not new_orders:
            logger.info("No new orders to save")
            return {}

        return self.api.create_orders(new_orders)

    def save_positions(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Persist positions, creating new ones and updating existing ones.

        Args:
            positions: Raw position dicts from IB broker.

        Returns:
            Dict with 'created' and/or 'updated' API responses
        """
        cache_positions = self.api.get_positions_data()
        cache_securities = {pos.get("security", "") for pos in cache_positions}

        result: Dict[str, Any] = {}

        new_positions = [
            {
                **p,
                "security": p.get("symbol", ""),
                "on_date": datetime.today().isoformat(),
                "timestamp": datetime.now().isoformat(),
            }
            for p in positions
            if p.get("symbol") not in cache_securities
        ]

        if new_positions:
            result["created"] = self.api.create_positions(new_positions)

        update_positions = {
            p.get("symbol", ""): {
                **p,
                "security": p.get("symbol", ""),
                "on_date": datetime.today().isoformat(),
                "timestamp": datetime.now().isoformat(),
            }
            for p in positions
            if p.get("symbol") in cache_securities
        }

        if update_positions:
            result["updated"] = self.update_positions(update_positions)

        return result

    def update_orders(self, orders: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Update orders in the API.

        Args:
            orders: Dict keyed by orderId with updated order dicts.
        """
        put_orders = [
            {
                **val,
                "security": val.get("symbol", ""),
                "limit_price": val.get("lmtPrice", 0),
                "on_date": datetime.today().isoformat(),
                "timestamp": datetime.now().isoformat(),
            }
            for val in orders.values()
        ]

        if not put_orders:
            logger.info("No orders to update")
            return {}

        return self.api.update_orders_data(put_orders)

    def update_positions(self, positions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Update positions in the API.

        Args:
            positions: Dict keyed by symbol with updated position dicts.
        """
        put_positions = [
            {
                **val,
                "security": val.get("symbol", ""),
                "on_date": datetime.today().isoformat(),
                "timestamp": datetime.now().isoformat(),
            }
            for val in positions.values()
        ]

        if not put_positions:
            logger.info("No positions to update")
            return {}

        return self.api.update_positions_data(put_positions)


class TbApi(TbApiService):
    """Main Trading Bot API entry point.

    Inherits all operations from TbApiService. Use this class
    as the primary interface for all TradingBot API interactions.

    Example::

        from tb_utils.apiwrapper.tbapi import TbApi

        api = TbApi()
        orders = api.get_orders()
    """

    def __init__(
        self, base_url: Optional[str] = None, verify_ssl: Optional[bool] = None
    ):
        super().__init__(api_client=TbApiCore(base_url=base_url, verify_ssl=verify_ssl))
