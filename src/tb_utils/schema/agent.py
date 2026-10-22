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
    # Gemini gatekeeper audit fields (None on the retired Ollama-era rows).
    signal_id: Optional[int] = None
    ai_provider: Optional[str] = None
    as_of: Optional[datetime] = None
    prompt_version: Optional[str] = None
    parsed_verdict: Optional[str] = None
    reason_codes: Optional[list[str]] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cost_inr: Optional[float] = None
    degraded: bool = False
    error_code: Optional[str] = None
    correlation_id: Optional[str] = None


class SignalVerdictSummary(BaseSchema):
    """The slim form of a gatekeeper verdict shown beside a signal (no evidence, no raw reply)."""

    signal_id: int
    verdict: Optional[str] = None  # APPROVE | REJECT | WAIT_PULLBACK; None when the call degraded
    degraded: bool = False
    error_code: Optional[str] = None
    confidence: Optional[float] = None
    reason_codes: list[str] = Field(default_factory=list)
    rationale: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    latency_ms: Optional[int] = None
    cost_inr: Optional[float] = None
    created_at: datetime


class GatekeeperSummaryResponse(BaseSchema):
    """How the gatekeeper has done over a window: volume, split of verdicts, and cost."""

    since: datetime
    judged: int
    degraded: int
    by_verdict: dict[str, int] = Field(default_factory=dict)
    cost_inr: float = 0.0
    avg_latency_ms: Optional[int] = None


class GeminiUsageBucket(BaseSchema):
    """HTTP attempts to Gemini in one slice of the day (an IST hour, or one model)."""

    label: str
    attempts: int = 0
    ok: int = 0
    rate_limited: int = 0
    failed: int = 0


class GeminiUsageResponse(BaseSchema):
    """Today's Gemini usage: what was sent, what it cost, and its daily limits."""

    day: str  # YYYY-MM-DD, IST
    max_calls_per_day: int  # 0 = no limit
    daily_budget_inr: float  # 0 = no limit
    answered_calls: int  # the counter the daily limit is checked against: calls Gemini answered
    cost_inr: float
    http_attempts: int  # every request sent, retries, fallback model and key rotation included
    http_ok: int
    http_rate_limited: int  # 429: quota
    http_server_errors: int  # 5xx
    http_other_failed: int  # timeouts and anything else
    verdicts_answered: int
    verdicts_degraded: int
    prompt_tokens: int
    completion_tokens: int
    active_key_index: Optional[int] = None
    quota_cooldown_seconds: int = 0  # >0: every key is out of quota and calls are paused
    by_model: list[GeminiUsageBucket] = Field(default_factory=list)
    by_hour: list[GeminiUsageBucket] = Field(default_factory=list)
    first_call_at: Optional[datetime] = None
    last_call_at: Optional[datetime] = None
