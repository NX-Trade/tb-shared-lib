"""Gemini over :class:`ExternalClient`: structured JSON out, every call recorded.

All traffic goes through the shared client, so each request and response is rate limited, circuit
broken and stored (redacted, compressed) in ``external_api_request`` under one correlation id. This
module adds what is specific to Gemini and must not be reinvented per caller:

* **Two API keys.** Key 1 is used until Gemini answers 429 (quota); the client then moves to key 2,
  remembers that in Redis for every worker, and alerts once an hour. Keys are sent in the
  ``x-goog-api-key`` header (redacted on the way into storage), never in the URL.
* **Two models.** The primary model is tried first; a transient failure (5xx, timeout) tries
  the fallback.
* **A daily budget.** Calls and an estimated rupee cost are counted per IST day in Redis; once
  either limit is
  reached the call raises :class:`GeminiBudgetExceeded` and the caller degrades.
* **Structured output.** A response schema is sent, and the reply must parse as JSON;
  anything else raises
  :class:`GeminiSchemaInvalid` and is never retried (it would fail the same way).
* **Determinism.** ``temperature=0`` and ``topP=1``.

The cost figure is an *estimate* from token counts and configurable prices, not a bill.
"""

import datetime as dt
import json
import logging
import os
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Optional

from tb_utils.http.client import ExternalClient
from tb_utils.http.errors import (
    CircuitOpen,
    ExternalApiError,
    GeminiBudgetExceeded,
    GeminiRateLimited,
    GeminiSchemaInvalid,
    GeminiTimeout,
    RateLimited,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from tb_utils.http.providers import ApiProviderEnum
from tb_utils.redis.keys import (
    get_gemini_active_key_key,
    get_gemini_alert_key,
    get_gemini_daily_counter_key,
)
from tb_utils.telegram import send_telegram_alert
from tb_utils.time import IST

logger = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_OUTPUT_TOKENS = 700
COUNTER_TTL_SECONDS = 3 * 24 * 3600
ALERT_DEBOUNCE_SECONDS = 3600


@dataclass(frozen=True)
class GeminiConfig:
    """Everything the client reads from the environment."""

    api_keys: tuple[str, ...]
    live_model: str
    eod_model: str
    max_calls_per_day: int = 2000
    daily_budget_inr: float = 200.0
    # Placeholder Flash-class prices: set the real ones in the environment (an estimate).
    price_in_usd_per_m: float = 0.30
    price_out_usd_per_m: float = 2.50
    usd_inr: float = 88.0

    @classmethod
    def from_env(cls) -> "GeminiConfig":
        keys = tuple(
            k for k in (os.getenv("GEMINI_API_KEY_1", ""), os.getenv("GEMINI_API_KEY_2", "")) if k
        )
        return cls(
            api_keys=keys,
            live_model=os.getenv("GEMINI_LIVE_MODEL", ""),
            eod_model=os.getenv("GEMINI_EOD_MODEL", ""),
            max_calls_per_day=int(os.getenv("GEMINI_MAX_CALLS_PER_DAY", "2000")),
            daily_budget_inr=float(os.getenv("GEMINI_DAILY_BUDGET_INR", "200")),
            price_in_usd_per_m=float(os.getenv("GEMINI_PRICE_INPUT_USD_PER_M", "0.30")),
            price_out_usd_per_m=float(os.getenv("GEMINI_PRICE_OUTPUT_USD_PER_M", "2.50")),
            usd_inr=float(os.getenv("GEMINI_USD_INR", "88")),
        )


@dataclass(frozen=True)
class GeminiResult:  # pylint: disable=too-many-instance-attributes
    """One successful structured response, with what is needed to audit it."""

    text: str
    parsed: Any
    model: str
    key_index: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_inr: float
    correlation_id: str
    finish_reason: str
    fallback_used: bool


def _today_ist() -> str:
    return dt.datetime.now(IST).strftime("%Y-%m-%d")


class GeminiClient:
    """Structured-JSON generation with key rotation, model fallback and a daily budget."""

    def __init__(
        self,
        redis_client: Any,
        config: GeminiConfig,
        external: Optional[ExternalClient] = None,
        session_factory: Optional[Any] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not config.api_keys:
            raise ValueError("No Gemini API key configured (GEMINI_API_KEY_1 / GEMINI_API_KEY_2).")
        self._redis = redis_client
        self._config = config
        self._timeout = timeout
        # One attempt per call here: retry and failover are decided below, per key and per model.
        self._external = external or ExternalClient(
            provider=ApiProviderEnum.GEMINI,
            redis_client=redis_client,
            session_factory=session_factory,
            max_attempts=1,
        )

    # ── Public ─────────────────────────────────────────────────────────────

    def generate(
        self,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        *,
        models: Optional[Sequence[str]] = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        correlation_id: Optional[str] = None,
    ) -> GeminiResult:
        """Ask for a JSON answer that fits ``response_schema``.

        ``models`` is the order to try (primary first); default: the live model, then the EOD one.
        Raises a typed :class:`ExternalApiError` subclass on any failure; the caller degrades.
        """
        self._check_budget()
        order = [m for m in (models or (self._config.live_model, self._config.eod_model)) if m]
        if not order:
            raise ValueError("No Gemini model configured (GEMINI_LIVE_MODEL / GEMINI_EOD_MODEL).")
        correlation_id = correlation_id or uuid.uuid4().hex
        body = self._body(system, user, response_schema, max_output_tokens)

        last_error: Optional[ExternalApiError] = None
        for position, model in enumerate(order):
            try:
                return self._call_model(model, body, correlation_id, fallback_used=position > 0)
            except (UpstreamUnavailable, UpstreamTimeout) as exc:
                last_error = exc
                logger.warning(
                    "Gemini model %s unavailable (%s); %s",
                    model,
                    exc.code,
                    "trying the next" if position + 1 < len(order) else "no fallback left",
                )
            except CircuitOpen:  # pylint: disable=try-except-raise
                raise  # the breaker is open for the provider: a second model would be refused too
        assert last_error is not None
        if isinstance(last_error, UpstreamTimeout):
            raise GeminiTimeout(
                last_error.message, provider="GEMINI", correlation_id=correlation_id
            ) from last_error
        raise last_error

    # ── One model, rotating keys on a quota error ──────────────────────────

    def _call_model(
        self, model: str, body: dict[str, Any], correlation_id: str, fallback_used: bool
    ) -> GeminiResult:
        url = f"{BASE_URL}/{model}:generateContent"
        started = time.time()
        tried: set[int] = set()
        while True:
            index = self._active_index()
            tried.add(index)
            try:
                response = self._external.request(
                    "POST",
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self._config.api_keys[index],
                    },
                    json_data=body,
                    correlation_id=correlation_id,
                    timeout=self._timeout,
                )
            except RateLimited as exc:
                if (
                    exc.status_code != 429
                ):  # our own limiter, not Gemini's quota: do not burn the other key
                    raise GeminiRateLimited(
                        exc.message,
                        provider="GEMINI",
                        correlation_id=correlation_id,
                        retry_after=exc.retry_after,
                    ) from exc
                other = self._other_index(index)
                if other is None or other in tried:
                    raise GeminiRateLimited(
                        "Gemini quota exhausted on every key",
                        provider="GEMINI",
                        status_code=429,
                        correlation_id=correlation_id,
                    ) from exc
                self._switch_key(other)
                continue
            except UpstreamTimeout as exc:
                raise GeminiTimeout(
                    exc.message, provider="GEMINI", endpoint=url, correlation_id=correlation_id
                ) from exc
            return self._result(
                response,
                model,
                index,
                int((time.time() - started) * 1000),
                correlation_id,
                fallback_used,
            )

    # ── Request and response ───────────────────────────────────────────────

    @staticmethod
    def _body(
        system: str, user: str, schema: dict[str, Any], max_output_tokens: int
    ) -> dict[str, Any]:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "topP": 1,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }

    def _result(
        self,
        response: Any,
        model: str,
        key_index: int,
        latency_ms: int,
        correlation_id: str,
        fallback_used: bool,
    ) -> GeminiResult:
        try:
            payload = response.json()
        except ValueError as exc:
            raise GeminiSchemaInvalid(
                "Gemini returned a non-JSON body", provider="GEMINI", correlation_id=correlation_id
            ) from exc
        candidates = payload.get("candidates") or []
        if not candidates:
            reason = (payload.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise GeminiSchemaInvalid(
                f"Gemini returned no answer ({reason})",
                provider="GEMINI",
                correlation_id=correlation_id,
            )
        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise GeminiSchemaInvalid(
                f"Gemini's answer is not valid JSON (finish {candidate.get('finishReason')})",
                provider="GEMINI",
                correlation_id=correlation_id,
            ) from exc
        usage = payload.get("usageMetadata") or {}
        prompt_tokens = int(usage.get("promptTokenCount") or 0)
        completion_tokens = int(usage.get("candidatesTokenCount") or 0)
        cost = self._cost_inr(prompt_tokens, completion_tokens)
        self._count(cost)
        return GeminiResult(
            text=text,
            parsed=parsed,
            model=payload.get("modelVersion") or model,
            key_index=key_index,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_inr=cost,
            correlation_id=correlation_id,
            finish_reason=str(candidate.get("finishReason") or ""),
            fallback_used=fallback_used,
        )

    # ── Keys ───────────────────────────────────────────────────────────────

    def _active_index(self) -> int:
        raw = self._redis.get(get_gemini_active_key_key())
        try:
            index = int(raw.decode() if isinstance(raw, bytes) else raw) if raw is not None else 0
        except (TypeError, ValueError):
            index = 0
        return index if 0 <= index < len(self._config.api_keys) else 0

    def _other_index(self, index: int) -> Optional[int]:
        return next((i for i in range(len(self._config.api_keys)) if i != index), None)

    def _switch_key(self, index: int) -> None:
        self._redis.set(get_gemini_active_key_key(), index)
        self._alert_once(
            "key_failover", f"🔑 <b>Gemini quota hit</b>: switched to API key {index + 1}."
        )

    def _alert_once(self, kind: str, message: str) -> None:
        if self._redis.set(get_gemini_alert_key(kind), "1", nx=True, ex=ALERT_DEBOUNCE_SECONDS):
            send_telegram_alert(message)

    # ── Budget ─────────────────────────────────────────────────────────────

    def _check_budget(self) -> None:
        day = _today_ist()
        calls = float(self._redis.get(get_gemini_daily_counter_key("calls", day)) or 0)
        cost = float(self._redis.get(get_gemini_daily_counter_key("cost_inr", day)) or 0)
        over_calls = self._config.max_calls_per_day > 0 and calls >= self._config.max_calls_per_day
        over_cost = self._config.daily_budget_inr > 0 and cost >= self._config.daily_budget_inr
        if over_calls or over_cost:
            self._alert_once(
                "budget",
                f"💸 <b>Gemini daily budget reached</b> ({int(calls)} calls, ₹{cost:.2f}). "
                "Verdicts are degraded until tomorrow.",
            )
            raise GeminiBudgetExceeded(
                f"Gemini daily budget reached ({int(calls)} calls, ₹{cost:.2f})", provider="GEMINI"
            )

    def _count(self, cost_inr: float) -> None:
        day = _today_ist()
        calls_key = get_gemini_daily_counter_key("calls", day)
        cost_key = get_gemini_daily_counter_key("cost_inr", day)
        self._redis.incr(calls_key)
        self._redis.expire(calls_key, COUNTER_TTL_SECONDS)
        self._redis.incrbyfloat(cost_key, cost_inr)
        self._redis.expire(cost_key, COUNTER_TTL_SECONDS)

    def _cost_inr(self, prompt_tokens: int, completion_tokens: int) -> float:
        usd = (
            prompt_tokens * self._config.price_in_usd_per_m
            + completion_tokens * self._config.price_out_usd_per_m
        ) / 1_000_000
        return round(usd * self._config.usd_inr, 4)
