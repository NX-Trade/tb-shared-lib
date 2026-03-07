"""Pydantic schemas for Broker and External API Requests."""

from datetime import datetime

from .base import BaseSchema


class BrokerResponse(BaseSchema):
    broker_id: int
    broker_name: str
    broker_type: str | None = None
    is_active: int
    created_at: datetime


class BrokerHealthLogResponse(BaseSchema):
    id: int
    broker_id: int | None = None
    layer: str | None = None
    status: str | None = None
    reason: str | None = None
    timestamp: datetime


class ExternalApiRequestCreate(BaseSchema):
    api_provider: int
    api_endpoint: str
    http_method: str
    request_headers: str | None = None
    request_payload: str | None = None
    correlation_id: str | None = None
    user_agent: str | None = None


class ExternalApiRequestResponse(ExternalApiRequestCreate):
    request_id: int
    http_status_code: int | None = None
    response_headers: str | None = None
    response_payload: str | None = None
    request_timestamp: datetime
    response_timestamp: datetime | None = None
    duration_ms: int | None = None
    is_success: int
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int
    circuit_breaker_state: int | None = None
    created_at: datetime
