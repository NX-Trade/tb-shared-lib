"""Request Maker and Circuit Breaker."""

import logging
import time
from typing import Any, Dict, Optional
import requests

from sqlalchemy.orm import Session
from ..models.broker import ExternalApiRequest

logger = logging.getLogger("tb-utils.requests.request_maker")


class CircuitBreakerError(Exception):
    """Exception raised when the circuit breaker is open."""

    pass


class RequestMaker:
    """A robust REST API wrapper with Circuit Breaker and Telemetry Logging.

    This class handles making external HTTP requests, tracking failures to open a circuit breaker
    if too many errors occur, and logging the request/response telemetry into the Database
    using the ExternalApiRequest model.
    """

    def __init__(
        self,
        api_provider_id: int,
        session: Session,
        max_failures: int = 5,
        reset_timeout_seconds: float = 60.0,
    ):
        """Initialize the Request Maker.

        Args:
            api_provider_id: ID of the API provider (e.g. 1 for NSE, 2 for BSE)
            session: SQLAlchemy DB Session for logging
            max_failures: Number of consecutive failures before opening the circuit
            reset_timeout_seconds: Time to wait before trying again when open
        """
        self.api_provider_id = api_provider_id
        self.session = session
        self.max_failures = max_failures
        self.reset_timeout_seconds = reset_timeout_seconds

        self.failure_count = 0
        self.state = "CLOSED"  # 'CLOSED', 'OPEN', 'HALF_OPEN'
        self.last_failure_time: Optional[float] = None
        self._session = requests.Session()

    def _before_request(self) -> None:
        """Check circuit breaker state before making a request."""
        if self.state == "OPEN":
            # Check if reset timeout has elapsed
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) > self.reset_timeout_seconds
            ):
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker entered HALF_OPEN state.")
            else:
                raise CircuitBreakerError(
                    "Circuit breaker is OPEN. Requests are blocked."
                )

    def _record_success(self) -> None:
        """Record a successful request to reset circuit breaker."""
        if self.state in ["OPEN", "HALF_OPEN"]:
            logger.info("Circuit breaker reset to CLOSED state.")
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_failure_time = None

    def _record_failure(self) -> None:
        """Record a failed request to handle circuit breaker logic."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.max_failures:
            self.state = "OPEN"
            logger.warning(
                f"Circuit breaker tripped to OPEN state after {self.failure_count} failures."
            )

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        correlation_id: str = None,
        timeout: float = 10.0,
    ) -> requests.Response:
        """Make an HTTP request with circuit breaking and logging.

        Args:
            method: HTTP Method ('GET', 'POST', etc.)
            url: The endpoint URL
            headers: Optional HTTP headers
            json_data: Optional JSON payload
            params: Optional URL parameters
            correlation_id: Optional correlation ID for tracing
            timeout: Request timeout in seconds

        Returns:
            The HTTP response object

        Raises:
            CircuitBreakerError: If the circuit is OPEN
            requests.RequestException: On severe network failures
        """
        self._before_request()

        start_time = time.time()

        # Track logging telemetry
        telemetry = ExternalApiRequest(
            api_provider=self.api_provider_id,
            api_endpoint=url,
            http_method=method.upper(),
            request_headers=str(headers) if headers else None,
            request_payload=str(json_data) if json_data else None,
            correlation_id=correlation_id,
            circuit_breaker_state=1
            if self.state == "CLOSED"
            else 2
            if self.state == "HALF_OPEN"
            else 0,
        )

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                params=params,
                timeout=timeout,
            )

            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)

            # Update Telemetry
            telemetry.http_status_code = response.status_code
            telemetry.response_headers = str(dict(response.headers))
            telemetry.response_payload = (
                response.text[:2000] if response.text else None
            )  # Trim large responses
            telemetry.duration_ms = duration_ms

            if response.ok:
                telemetry.is_success = 1
                self._record_success()
            else:
                telemetry.is_success = 0
                telemetry.error_code = str(response.status_code)
                telemetry.error_message = response.reason
                self._record_failure()

            self._log_telemetry(telemetry)
            return response

        except requests.RequestException as e:
            end_time = time.time()
            telemetry.duration_ms = int((end_time - start_time) * 1000)
            telemetry.is_success = 0
            telemetry.error_message = str(e)

            self._record_failure()
            self._log_telemetry(telemetry)
            raise

    def _log_telemetry(self, telemetry: ExternalApiRequest) -> None:
        """Safely save telemetry to the database."""
        try:
            self.session.add(telemetry)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            logger.error("Failed to save external API telemetry to DB: %s", str(e))
