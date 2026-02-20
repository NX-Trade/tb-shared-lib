"""Pydantic schemas for Broker and External API Requests."""

from datetime import datetime
from typing import Optional
from .base import BaseSchema


class BrokerResponse(BaseSchema):
    broker_id: int
    broker_name: str
    broker_type: Optional[str] = None
    is_active: int
    created_at: datetime


class BrokerHealthLogResponse(BaseSchema):
    id: int
    broker_id: Optional[int] = None
    layer: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    timestamp: datetime


class ExternalApiRequestCreate(BaseSchema):
    api_provider: int
    api_endpoint: str
    http_method: str
    request_headers: Optional[str] = None
    request_payload: Optional[str] = None
    correlation_id: Optional[str] = None
    user_agent: Optional[str] = None


class ExternalApiRequestResponse(ExternalApiRequestCreate):
    request_id: int
    http_status_code: Optional[int] = None
    response_headers: Optional[str] = None
    response_payload: Optional[str] = None
    request_timestamp: datetime
    response_timestamp: Optional[datetime] = None
    duration_ms: Optional[int] = None
    is_success: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    circuit_breaker_state: Optional[int] = None
    created_at: datetime
