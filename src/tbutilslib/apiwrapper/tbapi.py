import functools
import json
import os
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
from ..schema import OrdersSchema, PositionsSchema
from ..utils.dtu import TODAY, parse_timestamp, parse_timestamp_to_str
from ..utils.enums import SecurityTypeEnum

name = os.path.basename(__file__)
logger = getLogger("tbutilslib." + __name__)


def request_decorator(func):
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
    """Base API client for making HTTP requests.

    This class provides the foundation for making HTTP requests with proper
    error handling, retries, and response processing.
    """

    def __init__(self, base_url: str, verify_ssl: Optional[bool] = None):
        """Initialize the API client.

        Args:
            base_url: Base URL for the API
            verify_ssl: Whether to verify SSL certificates
        """
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.headers = {}

    def set_headers(self, headers: Dict[str, str]) -> None:
        """Set headers for API requests.

        Args:
            headers: Headers to set
        """
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
        """Make an HTTP request with retry logic.

        Args:
            method: HTTP method (get, post, put, delete)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data
            retry_codes: HTTP status codes to retry on
            max_retries: Maximum number of retries
            retry_wait: Wait time between retries in seconds

        Returns:
            Response object

        Raises:
            APIException: If the request fails after retries
        """
        if retry_codes is None:
            retry_codes = [429, 500, 502, 503, 504]

        url = (
            endpoint
            if endpoint.startswith("http")
            else f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        )

        # Convert Pydantic models to dict if needed
        if isinstance(data, BaseModel):
            data = data.model_dump()

        # Prepare request kwargs
        kwargs = {"params": params, "headers": self.headers, "verify": self.verify_ssl}

        # Add data based on method
        if method.lower() in ["post", "put", "patch"] and data is not None:
            kwargs["json"] = data

        # Retry logic
        for attempt in range(max_retries):
            try:
                response = requests.request(method, url, **kwargs)

                # If success or not a retry code, return immediately
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

                # Last attempt, return the error response
                if attempt == max_retries - 1:
                    return response

                # Wait before retry
                time.sleep(retry_wait)

            except (requests.RequestException, IOError) as e:
                # Last attempt, re-raise
                if attempt == max_retries - 1:
                    raise

                logger.warning(
                    "Request failed with exception: %s. Attempt %s of %s",
                    str(e),
                    attempt + 1,
                    max_retries,
                )
                time.sleep(retry_wait)

        # This should not be reached, but just in case
        raise errors.TradingBotAPIException("Maximum retries exceeded")

    def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Union[List, Dict[str, Any], BaseModel]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a request and process the response.

        Args:
            method: HTTP method (get, post, put, delete)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters

        Returns:
            JSON response as a dictionary

        Raises:
            APIException: If the request fails
        """
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
        """Make a GET request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response as a dictionary
        """
        return self.request("get", endpoint, params=params)

    def post(
        self, endpoint: str, data: Union[List, Dict[str, Any], BaseModel]
    ) -> Dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            data: Request body data

        Returns:
            JSON response as a dictionary
        """
        return self.request("post", endpoint, data=data)

    def put(
        self, endpoint: str, data: Union[List, Dict[str, Any], BaseModel]
    ) -> Dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path
            data: Request body data

        Returns:
            JSON response as a dictionary
        """
        return self.request("put", endpoint, data=data)

    def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path

        Returns:
            JSON response as a dictionary
        """
        return self.request("delete", endpoint)


class TbApiCore(ApiClient):
    """Core Trading Bot API wrapper for interacting with the TradingBot backend.

    This class provides basic CRUD operations against the TradingBot API.
    It handles authentication, request formatting, and response parsing.
    """

    def __init__(
        self, base_url: Optional[str] = None, verify_ssl: Optional[bool] = None
    ):
        """Initialize the TbApi instance.

        Args:
            base_url: Optional base URL for the API. Defaults to TbApiPathConfig.BASE_URI.
            verify_ssl: Whether to verify SSL certificates. Defaults to None (system default).
        """
        super().__init__(base_url or TbApiPathConfig.BASE_URI, verify_ssl)
        self.x_force_delete = False
        self._make_tb_api_headers()

    def _make_tb_api_headers(self) -> None:
        """Set up the headers for API requests."""
        headers = TbApiPathConfig.headers.copy()
        if self.x_force_delete:
            headers.update({"X-Force-Delete": "true"})
        self.set_headers(headers)

    def set_force_delete(self, force_delete: bool = True) -> None:
        """Set the X-Force-Delete header flag.

        Args:
            force_delete: Whether to force delete operations. Defaults to True.
        """
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
        """Make a request to the TradingBot API and handle responses.

        Args:
            method: HTTP method (get, post, put, delete)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters

        Returns:
            JSON response as a dictionary

        Raises:
            TradingBotAPIException: If the request fails
        """
        try:
            # Use the parent class's _make_request method instead of duplicating logic
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
        """Make a GET request to the API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response as a dictionary
        """
        return self.request("get", endpoint, params=params)

    def post(self, endpoint: str, data: Union[List, Dict[str, Any]]) -> Dict[str, Any]:
        """Make a POST request to the API.

        Args:
            endpoint: API endpoint path
            data: Request body data

        Returns:
            JSON response as a dictionary
        """
        return self.request("post", endpoint, data=data)

    def put(self, endpoint: str, data: Union[List, Dict[str, Any]]) -> Dict[str, Any]:
        """Make a PUT request to the API.

        Args:
            endpoint: API endpoint path
            data: Request body data

        Returns:
            JSON response as a dictionary or empty dict on error
        """
        try:
            if isinstance(data, dict):
                return self.request("put", endpoint, data=data)

            if isinstance(data, list):
                results = {}
                for item in data:
                    result = self.request("put", endpoint, data=item)
                    results.update(result)
                return results

            return {}
        except errors.TradingBotAPIException as e:
            logger.warning("PUT request failed: %s", e, exc_info=True)
            return {}

    def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make a DELETE request to the API.

        Args:
            endpoint: API endpoint path

        Returns:
            JSON response as a dictionary
        """
        self.set_force_delete(True)
        return self.request("delete", endpoint)

    # Basic CRUD endpoint methods
    def get_equity(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch equity data from TbApi.

        Args:
            on_date: Date for which to fetch equity data

        Returns:
            List of equity data
        """
        endpoint = f"{TbApiPathConfig.EQUITY}/{on_date}"
        return self.get(endpoint)

    def get_historical_derivatives(
        self, security: Optional[str] = None, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get historical derivatives data.

        Args:
            security: Security symbol
            params: Additional query parameters

        Returns:
            Historical derivatives data
        """
        endpoint = TbApiPathConfig.HISTORICAL_DERIVATIVES
        if security:
            endpoint = f"{endpoint}/{security}"
        return self.get(endpoint, params=params)

    def get_fii_dii(self) -> Dict[str, Any]:
        """Fetch FII-DII investment data.

        Returns:
            FII-DII investment data
        """
        endpoint = TbApiPathConfig.FII_DII
        return self.get(endpoint)

    def get_trading_dates_data(self) -> Dict[str, Any]:
        """Fetch all trading dates data.

        Returns:
            Trading dates response object
        """
        endpoint = TbApiPathConfig.TRADING_DATES
        return self.get(endpoint)

    def get_orders_data(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch orders data from TbApi.

        Args:
            on_date: Date for which to fetch orders

        Returns:
            List of orders
        """
        endpoint = f"{TbApiPathConfig.ORDERS}/{on_date}"
        return self.get(endpoint)

    def get_positions_data(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch positions data from TbApi.

        Args:
            on_date: Date for which to fetch positions

        Returns:
            List of positions
        """
        endpoint = f"{TbApiPathConfig.POSITIONS}/{on_date}"
        return self.get(endpoint)

    def get_expiry_dates_data(
        self, security_type: str = SecurityTypeEnum.EQUITY.value
    ) -> List[str]:
        """Fetch expiry dates for a security type.

        Args:
            security_type: Type of security (e.g., equity, futures)

        Returns:
            List of expiry dates
        """
        endpoint = f"{TbApiPathConfig.EXPIRY_DATES}/{security_type.lower()}"
        return self.get(endpoint)

    def get_events_data(
        self,
        params: Optional[Dict[str, Any]] = None,
        securities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch events data from TbApi.

        Args:
            query: Additional query parameters
            securities: List of securities to filter by

        Returns:
            List of events
        """
        endpoint = TbApiPathConfig.EVENTS_PATH
        params = params or {}
        if securities:
            logger.info("Events Count of securities: %d", len(securities))
            if len(securities) < 80:
                params.update({"security__in": json.dumps(securities)})
            else:
                logger.warning("Count of securities is greater than permissible limit.")
        return self.get(endpoint, params=params)

    def create_orders(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create orders in TbApi.

        Args:
            orders_data: List of orders data to create

        Returns:
            API response
        """
        endpoint = f"{TbApiPathConfig.ORDERS}/{TODAY}"
        return self.post(endpoint, data=orders_data)

    def create_positions(self, positions_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create positions in TbApi.

        Args:
            positions_data: List of positions data to create

        Returns:
            API response
        """
        endpoint = f"{TbApiPathConfig.POSITIONS}/{TODAY}"
        return self.post(endpoint, data=positions_data)

    def update_orders_data(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Update orders in TbApi.

        Args:
            orders_data: List of orders data to update

        Returns:
            API response
        """
        endpoint = f"{TbApiPathConfig.ORDERS}/{TODAY}"
        return self.put(endpoint, data=orders_data)

    def update_positions_data(
        self, positions_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Update positions in TbApi.

        Args:
            positions_data: List of positions data to update

        Returns:
            API response
        """
        endpoint = f"{TbApiPathConfig.POSITIONS}/{TODAY}"
        return self.put(endpoint, data=positions_data)


class TbApiService:
    """Service class for Trading Bot API operations.

    This class provides higher-level business logic operations that build on
    the core API operations provided by TbApiCore.
    """

    def __init__(self, api_client: Optional[TbApiCore] = None):
        """Initialize the TbApiService instance.

        Args:
            api_client: Optional TbApiCore instance. If not provided, a new one will be created.
        """
        self.api = api_client or TbApiCore()

    def get_security_in_focus(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch securities in focus from TbApi.

        Args:
            on_date: Date for which to fetch securities in focus

        Returns:
            List of securities in focus
        """
        return self.api.get_equity(on_date)

    def get_investment(self) -> Dict[str, Any]:
        """Fetch FII-DII investment data.

        Returns:
            FII-DII investment data
        """
        return self.api.get_fii_dii()

    def get_past_trading_dates(self, count: int) -> List[str]:
        """Fetch past trading dates.

        Args:
            count: Number of past trading dates to retrieve

        Returns:
            List of trading dates
        """
        fii_dii = self.api.get_fii_dii()
        dates = sorted(list({item["on_date"] for item in fii_dii}), reverse=True)
        return dates[:count]

    def get_trading_dates(self) -> Dict[str, Any]:
        """Fetch all trading dates.

        Returns:
            Trading dates response object
        """
        return self.api.get_trading_dates_data()

    def get_orders(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch orders from TbApi.

        Args:
            on_date: Date for which to fetch orders

        Returns:
            List of orders
        """
        return self.api.get_orders_data(on_date)

    def get_positions(self, on_date: str = TODAY) -> List[Dict[str, Any]]:
        """Fetch positions from TbApi.

        Args:
            on_date: Date for which to fetch positions

        Returns:
            List of positions
        """
        return self.api.get_positions_data(on_date)

    def get_expiry_dates(
        self, security_type: str = SecurityTypeEnum.EQUITY.value
    ) -> List[str]:
        """Fetch expiry dates for a security type.

        Args:
            security_type: Type of security (e.g., equity, futures)

        Returns:
            List of expiry dates
        """
        return self.api.get_expiry_dates_data(security_type)

    def get_events(
        self,
        query: Optional[Dict[str, Any]] = None,
        securities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch events from TbApi.

        Args:
            query: Additional query parameters
            securities: List of securities to filter by

        Returns:
            List of events
        """
        return self.api.get_events_data(query, securities)

    def get_most_traded_securities(
        self, key: str = "totalTradedValue", count: int = 3, on_date: str = TODAY
    ) -> List[Dict[str, Any]]:
        """Fetch most traded securities from NSE.

        Args:
            key: Key to sort by (e.g., totalTradedValue)
            count: Number of securities to return
            on_date: Date for which to fetch securities

        Returns:
            List of most traded securities
        """
        items = self.api.get_equity(on_date)

        # Filter out NIFTY
        items = [item for item in items if item["security"] != "NIFTY"]

        # Get the latest timestamp
        if not items:
            return []

        latest_ts = max(parse_timestamp(item["timestamp"]) for item in items)
        latest_ts_str = parse_timestamp_to_str(latest_ts)

        # Filter items by latest timestamp
        latest_ts_payload = [
            item for item in items if item["timestamp"] == latest_ts_str
        ]

        # Sort by the specified key
        latest_ts_payload.sort(key=lambda x: x.get(key, 0), reverse=True)

        return latest_ts_payload[:count]

    def save_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save orders to TbApi.

        Args:
            orders: List of orders to save

        Returns:
            API response
        """
        # Get existing orders to avoid duplicates
        cache_orders = self.api.get_orders_data()
        cache_order_ids = {od.get("orderId") for od in cache_orders if "orderId" in od}

        # Prepare orders for posting, excluding existing ones
        post_orders = [
            {
                **order,
                "security": order.get("symbol", ""),
                "limit_price": order.get("lmtPrice", 0),
                "on_date": datetime.today(),
                "timestamp": datetime.now(),
            }
            for order in orders
            if order.get("orderId") not in cache_order_ids
        ]

        if not post_orders:
            logger.info("No new orders to save")
            return {}

        # Use OrdersSchema for validation
        post_orders = OrdersSchema().dump(post_orders, many=True)
        return self.api.create_orders(post_orders)

    def save_positions(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save positions to TbApi.

        Args:
            positions: List of positions to save

        Returns:
            API response
        """
        # Get existing positions to determine which to create vs update
        cache_positions = self.api.get_positions_data()
        cache_securities = {
            pos.get("security", "") for pos in cache_positions if "security" in pos
        }

        # Prepare new positions for posting
        new_positions = [
            {
                **position,
                "security": position.get("symbol", ""),
                "on_date": datetime.today(),
                "timestamp": datetime.now(),
            }
            for position in positions
            if position.get("symbol") not in cache_securities
        ]

        result = {}

        # Save new positions
        if new_positions:
            post_positions = PositionsSchema().dump(new_positions, many=True)
            result["created"] = self.api.create_positions(post_positions)

        # Prepare positions for updating
        update_positions = {
            position.get("symbol", ""): {
                **position,
                "security": position.get("symbol", ""),
                "on_date": datetime.today(),
                "timestamp": datetime.now(),
            }
            for position in positions
            if position.get("symbol") in cache_securities
        }

        # Update existing positions
        if update_positions:
            result["updated"] = self.update_positions(update_positions)

        return result

    def update_orders(self, orders: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Update orders in TbApi.

        Args:
            orders: Dictionary of orders to update, keyed by order ID

        Returns:
            API response
        """
        # Prepare orders for updating
        put_orders = [
            {
                **val,
                "security": val.get("symbol", ""),
                "limit_price": val.get("lmtPrice", 0),
                "on_date": datetime.today(),
                "timestamp": datetime.now(),
            }
            for oid, val in orders.items()
        ]

        if not put_orders:
            logger.info("No orders to update")
            return {}

        # Use OrdersSchema for validation
        put_orders = OrdersSchema().dump(put_orders, many=True)
        return self.api.update_orders_data(put_orders)

    def update_positions(self, positions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Update positions in TbApi.

        Args:
            positions: Dictionary of positions to update, keyed by symbol

        Returns:
            API response
        """
        # Prepare positions for updating
        put_positions = [
            {
                **val,
                "security": val.get("symbol", ""),
                "on_date": datetime.today(),
                "timestamp": datetime.now(),
            }
            for val in positions.values()
        ]

        if not put_positions:
            logger.info("No positions to update")
            return {}

        # Use PositionsSchema for validation
        put_positions = PositionsSchema().dump(put_positions, many=True)
        return self.api.update_positions_data(put_positions)


class TbApi(TbApiService):
    """Trading Bot API wrapper for backward compatibility.

    This class inherits from TbApiService to maintain backward compatibility
    with existing code that uses the TbApi class.
    """

    def __init__(
        self, base_url: Optional[str] = None, verify_ssl: Optional[bool] = None
    ):
        """Initialize the TbApi instance.

        Args:
            base_url: Optional base URL for the API. Defaults to TbApiPathConfig.BASE_URI.
            verify_ssl: Whether to verify SSL certificates. Defaults to None (system default).
        """
        # Create a TbApiCore instance with the provided parameters
        api_client = TbApiCore(base_url=base_url, verify_ssl=verify_ssl)
        # Initialize the TbApiService with the created client
        super().__init__(api_client=api_client)
