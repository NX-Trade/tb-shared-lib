# pylint: disable=unused-argument  # fakes mirror the real signatures
"""GeminiClient: structured output, key failover, model fallback, budget, typed errors."""

import json
from unittest.mock import patch

import pytest

from tb_utils.http.errors import (
    CircuitOpen,
    GeminiBudgetExceeded,
    GeminiRateLimited,
    GeminiSchemaInvalid,
    GeminiTimeout,
    RateLimited,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from tb_utils.http.gemini import GeminiClient, GeminiConfig
from tb_utils.http.redaction import REDACTED, redact_headers

SCHEMA = {"type": "OBJECT", "properties": {"verdict": {"type": "STRING"}}, "required": ["verdict"]}


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        return True

    def incr(self, key):
        self.store[key] = str(int(float(self.store.get(key, 0))) + 1)

    def incrbyfloat(self, key, amount):
        self.store[key] = str(float(self.store.get(key, 0)) + amount)

    def expire(self, key, seconds):
        return True


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


def answer(
    text='{"verdict": "APPROVE"}',
    prompt=1000,
    completion=100,
    version="gemini-live-001",
    finish="STOP",
):
    return FakeResponse(
        {
            "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
            "usageMetadata": {"promptTokenCount": prompt, "candidatesTokenCount": completion},
            "modelVersion": version,
        }
    )


class FakeExternal:
    """Plays back a script of responses or exceptions and records every request."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def request(
        self, method, url, headers=None, json_data=None, correlation_id=None, timeout=None, **_
    ):
        self.calls.append(
            {"url": url, "headers": headers, "body": json_data, "correlation_id": correlation_id}
        )
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


CONFIG = GeminiConfig(
    api_keys=("key-one", "key-two"),
    live_model="live-model",
    eod_model="eod-model",
    max_calls_per_day=5,
    daily_budget_inr=50.0,
)


def client(script, config=CONFIG, redis=None):
    redis = redis or FakeRedis()
    external = FakeExternal(script)
    return GeminiClient(redis, config, external=external), external, redis


def quota():
    return RateLimited("quota", provider="GEMINI", status_code=429)


class TestSuccess:
    def test_returns_the_parsed_answer_with_tokens_and_cost(self):
        gemini, _, _ = client([answer()])
        result = gemini.generate("sys", "user", SCHEMA)
        assert result.parsed == {"verdict": "APPROVE"}
        assert (result.prompt_tokens, result.completion_tokens) == (1000, 100)
        assert result.model == "gemini-live-001"
        assert result.fallback_used is False
        # 1000 in x $0.30/M + 100 out x $2.50/M = $0.00055, at 88 INR/USD
        assert result.cost_inr == pytest.approx(0.0484, abs=0.0001)

    def test_asks_for_deterministic_json_against_the_schema(self):
        gemini, external, _ = client([answer()])
        gemini.generate("be careful", "the signal", SCHEMA, max_output_tokens=500)
        call = external.calls[0]
        cfg = call["body"]["generationConfig"]
        assert (cfg["temperature"], cfg["topP"], cfg["maxOutputTokens"]) == (0, 1, 500)
        assert cfg["responseMimeType"] == "application/json"
        assert cfg["responseSchema"] == SCHEMA
        assert call["body"]["systemInstruction"]["parts"][0]["text"] == "be careful"
        assert call["body"]["contents"][0]["parts"][0]["text"] == "the signal"

    def test_the_key_goes_in_a_header_never_the_url(self):
        gemini, external, _ = client([answer()])
        gemini.generate("s", "u", SCHEMA)
        call = external.calls[0]
        assert call["headers"]["x-goog-api-key"] == "key-one"
        assert "key-one" not in call["url"]
        assert call["url"].endswith("/live-model:generateContent")

    def test_the_stored_copy_of_that_header_is_redacted(self):
        assert redact_headers(
            {"x-goog-api-key": "key-one", "Content-Type": "application/json"}
        ) == {
            "x-goog-api-key": REDACTED,
            "Content-Type": "application/json",
        }

    def test_every_attempt_of_one_call_shares_a_correlation_id(self):
        gemini, external, _ = client([quota(), answer()])
        result = gemini.generate("s", "u", SCHEMA)
        assert {c["correlation_id"] for c in external.calls} == {result.correlation_id}


class TestKeyFailover:
    def test_a_429_moves_to_the_second_key_and_remembers_it(self):
        gemini, external, _ = client([quota(), answer(), answer()])
        with patch("tb_utils.http.gemini.send_telegram_alert") as alert:
            first = gemini.generate("s", "u", SCHEMA)
            second = gemini.generate("s", "u", SCHEMA)
        assert [c["headers"]["x-goog-api-key"] for c in external.calls] == [
            "key-one",
            "key-two",
            "key-two",
        ]
        assert (first.key_index, second.key_index) == (1, 1)
        alert.assert_called_once()  # told once, not on every call

    def test_both_keys_over_quota_is_a_typed_error(self):
        gemini, _, _ = client([quota(), quota()])
        with patch("tb_utils.http.gemini.send_telegram_alert"), pytest.raises(GeminiRateLimited):
            gemini.generate("s", "u", SCHEMA)

    def test_our_own_limiter_does_not_burn_the_other_key(self):
        gemini, external, redis = client([RateLimited("per-second budget", provider="GEMINI")])
        with pytest.raises(GeminiRateLimited):
            gemini.generate("s", "u", SCHEMA)
        assert len(external.calls) == 1
        assert redis.get("gemini:active_key_index") is None


class TestModelFallback:
    def test_a_transient_failure_tries_the_fallback_model(self):
        gemini, external, _ = client(
            [UpstreamUnavailable("503", provider="GEMINI"), answer(version="eod-001")]
        )
        result = gemini.generate("s", "u", SCHEMA)
        assert [c["url"].split("/")[-1] for c in external.calls] == [
            "live-model:generateContent",
            "eod-model:generateContent",
        ]
        assert result.fallback_used is True

    def test_both_models_down_raises_the_upstream_error(self):
        gemini, _, _ = client(
            [
                UpstreamUnavailable("503", provider="GEMINI"),
                UpstreamUnavailable("503", provider="GEMINI"),
            ]
        )
        with pytest.raises(UpstreamUnavailable):
            gemini.generate("s", "u", SCHEMA)

    def test_models_can_be_ordered_by_the_caller(self):
        gemini, external, _ = client([answer()])
        gemini.generate("s", "u", SCHEMA, models=("eod-model", "live-model"))
        assert external.calls[0]["url"].endswith("/eod-model:generateContent")

    def test_an_open_breaker_is_not_retried_on_another_model(self):
        gemini, external, _ = client([CircuitOpen("open", provider="GEMINI")])
        with pytest.raises(CircuitOpen):
            gemini.generate("s", "u", SCHEMA)
        assert len(external.calls) == 1


class TestTimeouts:
    def test_a_timeout_is_a_gemini_timeout(self):
        gemini, _, _ = client(
            [UpstreamTimeout("slow", provider="GEMINI"), UpstreamTimeout("slow", provider="GEMINI")]
        )
        with pytest.raises(GeminiTimeout):
            gemini.generate("s", "u", SCHEMA)


class TestSchemaFailures:
    def test_an_answer_that_is_not_json_is_invalid_and_not_retried(self):
        gemini, external, _ = client([answer(text="I think this is fine", finish="MAX_TOKENS")])
        with pytest.raises(GeminiSchemaInvalid, match="MAX_TOKENS"):
            gemini.generate("s", "u", SCHEMA)
        assert len(external.calls) == 1

    def test_a_blocked_prompt_is_invalid(self):
        blocked = FakeResponse({"promptFeedback": {"blockReason": "SAFETY"}})
        gemini, _, _ = client([blocked])
        with pytest.raises(GeminiSchemaInvalid, match="SAFETY"):
            gemini.generate("s", "u", SCHEMA)

    def test_a_non_json_body_is_invalid(self):
        gemini, _, _ = client([FakeResponse("<html>oops</html>")])
        with pytest.raises(GeminiSchemaInvalid):
            gemini.generate("s", "u", SCHEMA)


class TestBudget:
    def test_the_call_limit_stops_further_calls_without_touching_the_network(self):
        config = GeminiConfig(
            api_keys=("k",), live_model="m", eod_model="", max_calls_per_day=2, daily_budget_inr=0
        )
        gemini, external, _ = client([answer(), answer(), answer()], config)
        gemini.generate("s", "u", SCHEMA)
        gemini.generate("s", "u", SCHEMA)
        with patch("tb_utils.http.gemini.send_telegram_alert"), pytest.raises(GeminiBudgetExceeded):
            gemini.generate("s", "u", SCHEMA)
        assert len(external.calls) == 2

    def test_the_rupee_limit_stops_calls_too(self):
        config = GeminiConfig(
            api_keys=("k",),
            live_model="m",
            eod_model="",
            max_calls_per_day=0,
            daily_budget_inr=0.05,
        )
        gemini, _, _ = client([answer(prompt=1000, completion=100), answer()], config)
        gemini.generate("s", "u", SCHEMA)  # costs about 0.048
        gemini.generate("s", "u", SCHEMA)  # 0.0968 total
        with patch("tb_utils.http.gemini.send_telegram_alert"), pytest.raises(GeminiBudgetExceeded):
            gemini.generate("s", "u", SCHEMA)

    def test_a_failed_call_does_not_use_budget(self):
        config = GeminiConfig(
            api_keys=("k",), live_model="m", eod_model="", max_calls_per_day=1, daily_budget_inr=0
        )
        gemini, _, _ = client([UpstreamUnavailable("503", provider="GEMINI"), answer()], config)
        with pytest.raises(UpstreamUnavailable):
            gemini.generate("s", "u", SCHEMA)
        gemini.generate("s", "u", SCHEMA)  # still allowed: the first call spent nothing


class TestConfiguration:
    def test_no_key_is_refused_up_front(self):
        with pytest.raises(ValueError, match="API key"):
            GeminiClient(FakeRedis(), GeminiConfig(api_keys=(), live_model="m", eod_model=""))

    def test_no_model_is_refused_up_front(self):
        gemini, _, _ = client([], GeminiConfig(api_keys=("k",), live_model="", eod_model=""))
        with pytest.raises(ValueError, match="model"):
            gemini.generate("s", "u", SCHEMA)

    def test_reads_keys_models_and_limits_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY_1", "a")
        monkeypatch.setenv("GEMINI_API_KEY_2", "b")
        monkeypatch.setenv("GEMINI_LIVE_MODEL", "live")
        monkeypatch.setenv("GEMINI_EOD_MODEL", "eod")
        monkeypatch.setenv("GEMINI_MAX_CALLS_PER_DAY", "10")
        config = GeminiConfig.from_env()
        assert config.api_keys == ("a", "b")
        assert (config.live_model, config.eod_model, config.max_calls_per_day) == (
            "live",
            "eod",
            10,
        )

    def test_a_single_key_is_enough(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY_1", "a")
        monkeypatch.delenv("GEMINI_API_KEY_2", raising=False)
        assert GeminiConfig.from_env().api_keys == ("a",)
