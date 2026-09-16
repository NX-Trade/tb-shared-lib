"""Pydantic schemas for Agent Verdicts and Agent Cluster status."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from .base import BaseSchema


class AgentVerdictResponse(BaseSchema):
    """Schema for returning Agent Verdict details."""

    verdict_id: UUID
    symbol: str
    trade_date: datetime
    agent_name: str
    model_name: str
    node: str
    approved: bool
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    input_context: Optional[dict[str, Any]] = Field(default_factory=dict)
    output_json: Optional[dict[str, Any]] = Field(default_factory=dict)
    latency_ms: Optional[int] = None
    created_at: datetime


class AgentClusterNodeStatus(BaseSchema):
    """Status for an individual agent Ollama node."""

    node_id: str
    name: str
    url: str
    online: bool
    latency_ms: Optional[int] = None
    models: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class AgentClusterStatusResponse(BaseSchema):
    """Consolidated status for the multi-agent cluster."""

    active_mode: str  # "MULTI_AGENT_CONSENSUS" or "PURE_MATH_ENSEMBLE"
    nodes: list[AgentClusterNodeStatus] = Field(default_factory=list)
    total_verdicts_24h: int = 0
    updated_at: datetime
