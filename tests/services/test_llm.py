import json

import httpx
import pytest

from app.services.llm import (
    DEFAULT_FALLBACK_MODELS,
    DEFAULT_MODEL,
    LLMResponse,
    TradeDialogue,
    FreeAgentPitch,
    OpenRouterClient,
)


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class DummyAsyncClient:
    def __init__(self, *_, **__):
        self.last_headers = None
        self.last_json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, path, *, headers, json):
        self.last_headers = headers
        self.last_json = json
        return DummyResponse(
            {
                "choices": [
                    {"message": {"content": "Recap text"}},
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "total_tokens": 150,
                    "estimated_cost": 0.0012,
                },
            }
        )


@pytest.mark.asyncio
async def test_openrouter_client_builds_payload(monkeypatch):
    dummy_client = DummyAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: dummy_client)
    client = OpenRouterClient(api_key="test-key", model=DEFAULT_MODEL)
    response = await client.complete(
        "system",
        "user",
        temperature=0.2,
        max_output_tokens=128,
        progress_summary="Seed schedule built",
        remaining_tasks="Simulate postseason",
        use_reasoning=True,
        reasoning_effort="high",
    )

    assert isinstance(response, LLMResponse)
    assert response.text == "Recap text"
    assert response.model == DEFAULT_MODEL
    assert response.fallback_used is False
    assert response.attempts == 1
    assert response.rate_limited is False
    assert response.prompt_tokens == 120
    assert response.completion_tokens == 30
    assert response.total_tokens == 150
    assert response.estimated_cost_usd == pytest.approx(0.0012)

    assert dummy_client.last_json["model"] == DEFAULT_MODEL
    assert dummy_client.last_json["temperature"] == 0.2
    assert dummy_client.last_json["max_output_tokens"] == 128
    assert dummy_client.last_json["messages"][0]["role"] == "system"
    assert "Progress Update" in dummy_client.last_json["messages"][1]["content"]
    assert dummy_client.last_json["reasoning"] == {"effort": "high"}
    assert dummy_client.last_headers["Authorization"] == "Bearer test-key"

    assert client.total_calls == 1
    assert client.total_prompt_tokens == 120
    assert client.total_completion_tokens == 30
    assert client.total_cost_usd == pytest.approx(0.0012)
    assert client.fallback_calls == 0
    assert client.rate_limit_events == 0


@pytest.mark.asyncio
async def test_openrouter_missing_key_raises(monkeypatch):
    client = OpenRouterClient(api_key=None)
    with pytest.raises(RuntimeError):
        await client.complete("system", "user")


class DummyHTTPError(httpx.HTTPStatusError):
    def __init__(self, status_code: int = 503) -> None:
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(status_code, request=request)
        super().__init__("service unavailable", request=request, response=response)


class DummyFailThenSucceedClient:
    def __init__(self, *_, **__):
        self.attempts = 0
        self.last_models = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, path, *, headers, json):
        self.attempts += 1
        self.last_models.append(json["model"])
        if self.attempts == 1:
            raise DummyHTTPError()
        return DummyResponse(
            {
                "choices": [
                    {"message": {"content": f"response from {json['model']}"}},
                ],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 10,
                    "total_tokens": 60,
                },
            }
        )


@pytest.mark.asyncio
async def test_openrouter_falls_back_to_secondary_model(monkeypatch):
    dummy_client = DummyFailThenSucceedClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: dummy_client)
    client = OpenRouterClient(
        api_key="key", model=DEFAULT_MODEL, fallback_models=DEFAULT_FALLBACK_MODELS
    )

    response = await client.complete("sys", "user")

    assert dummy_client.attempts == 2
    assert dummy_client.last_models == [DEFAULT_MODEL, DEFAULT_FALLBACK_MODELS[0]]
    assert response.text == f"response from {DEFAULT_FALLBACK_MODELS[0]}"
    assert response.model == DEFAULT_FALLBACK_MODELS[0]
    assert response.fallback_used is True
    assert client.fallback_calls == 1
    assert client.total_calls == 1


class DummyAlwaysFailClient:
    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, *_, **__):
        raise DummyHTTPError()


@pytest.mark.asyncio
async def test_openrouter_raises_after_all_models_fail(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyAlwaysFailClient())
    client = OpenRouterClient(api_key="key", model="model-a", fallback_models=["model-b"])

    with pytest.raises(RuntimeError) as exc:
        await client.complete("sys", "user")

    assert "failed for all" in str(exc.value).lower()


class DummyRateLimitThenSuccessClient:
    def __init__(self, *_, **__):
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, path, *, headers, json):
        self.calls += 1
        if self.calls == 1:
            raise DummyHTTPError(status_code=429)
        return DummyResponse(
            {
                "choices": [
                    {"message": {"content": "rate limit ok"}},
                ],
                "usage": {
                    "prompt_tokens": 25,
                    "completion_tokens": 5,
                    "total_tokens": 30,
                },
            }
        )


@pytest.mark.asyncio
async def test_openrouter_marks_rate_limit_and_tracks_metric(monkeypatch):
    dummy_client = DummyRateLimitThenSuccessClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: dummy_client)
    client = OpenRouterClient(api_key="key", model=DEFAULT_MODEL)

    response = await client.complete("sys", "user")

    assert response.text == "rate limit ok"
    assert response.rate_limited is True
    assert client.rate_limit_events == 1
    assert client.total_calls == 1


@pytest.mark.asyncio
async def test_generate_trade_dialogue_returns_structured_payload(monkeypatch):
    payload = {
        "summary": "Bears consider Bills' proposal but want more future capital.",
        "team_positions": {
            "team_a": "Chicago believes they are giving up more immediate value.",
            "team_b": "Buffalo is comfortable parting with future picks for win-now help.",
        },
        "negotiation_points": [
            "Chicago wants an additional Day 2 pick or player swap.",
            "Buffalo highlights cap flexibility after the move.",
        ],
    }

    async def fake_complete(self, *args, **kwargs):
        return LLMResponse(
            text=json.dumps(payload),
            model="stub",
            fallback_used=False,
            attempts=1,
            rate_limited=False,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_usd=0.002,
        )

    monkeypatch.setattr(OpenRouterClient, "complete", fake_complete, raising=False)

    client = OpenRouterClient(api_key="key")
    dialogue = await client.generate_trade_dialogue(
        {
            "teams": {
                "team_a": {"name": "Chicago Bears", "assets": [1, 72]},
                "team_b": {"name": "Buffalo Bills", "assets": [28, 60, 92]},
            },
            "evaluation": {"team_a_value": 3600, "team_b_value": 2500, "delta": 1100},
            "narrative_focus": "Balancing current starters versus future draft capital.",
            "progress_summary": "Initial valuation complete for Bears vs Bills trade.",
            "remaining_tasks": "Decide whether to counter-offer or accept the proposal.",
        }
    )

    assert isinstance(dialogue, TradeDialogue)
    assert dialogue.summary.startswith("Bears")
    assert "Chicago" in dialogue.team_positions["team_a"]
    assert len(dialogue.negotiation_points) == 2


@pytest.mark.asyncio
async def test_generate_trade_dialogue_rejects_invalid_payload(monkeypatch):
    async def fake_complete(self, *args, **kwargs):
        return LLMResponse(
            text=json.dumps({"summary": "Missing details"}),
            model="stub",
            fallback_used=False,
            attempts=1,
            rate_limited=False,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(OpenRouterClient, "complete", fake_complete, raising=False)

    client = OpenRouterClient(api_key="key")
    with pytest.raises(ValueError):
        await client.generate_trade_dialogue({"teams": {}})


@pytest.mark.asyncio
async def test_generate_free_agent_pitch_returns_structured_payload(monkeypatch):
    payload = {
        "summary": "Receiver is intrigued by the front-loaded offer.",
        "team_pitch": "The team sells a contender window and feature role.",
        "player_reaction": "Agent requests clarity on incentives and guarantees.",
        "next_steps": [
            "Team schedules follow-up call with agent",
            "Agent reviews guarantee structure with player",
        ],
    }

    async def fake_complete(self, *args, **kwargs):
        return LLMResponse(
            text=json.dumps(payload),
            model="stub",
            fallback_used=False,
            attempts=1,
            rate_limited=False,
            prompt_tokens=80,
            completion_tokens=40,
            total_tokens=120,
            estimated_cost_usd=0.001,
        )

    monkeypatch.setattr(OpenRouterClient, "complete", fake_complete, raising=False)

    client = OpenRouterClient(api_key="key")
    pitch = await client.generate_free_agent_pitch(
        {
            "team_name": "Denver Broncos",
            "player_name": "Top Receiver",
            "player_position": "WR",
            "offer": {
                "years": 3,
                "total_value": 54_000_000,
                "signing_bonus": 18_000_000,
                "guarantees": 45_000_000,
                "incentives": ["Pro Bowl", "Super Bowl MVP"],
            },
            "metrics": {
                "apy": 18_000_000,
                "guaranteed_percentage": 0.83,
                "signing_bonus_proration": 6_000_000,
                "market_delta": 2_000_000,
                "risk_flags": ["Guarantees exceed 80% of total value"],
            },
            "progress_summary": "Offer drafted for top receiver target.",
            "remaining_tasks": "Confirm bonuses and agent feedback.",
        }
    )

    assert isinstance(pitch, FreeAgentPitch)
    assert pitch.summary.startswith("Receiver")
    assert "contender" in pitch.team_pitch.lower()
    assert len(pitch.next_steps) == 2


@pytest.mark.asyncio
async def test_generate_free_agent_pitch_rejects_invalid_payload(monkeypatch):
    async def fake_complete(self, *args, **kwargs):
        return LLMResponse(
            text=json.dumps({"summary": "No steps"}),
            model="stub",
            fallback_used=False,
            attempts=1,
            rate_limited=False,
            prompt_tokens=50,
            completion_tokens=20,
            total_tokens=70,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(OpenRouterClient, "complete", fake_complete, raising=False)

    client = OpenRouterClient(api_key="key")
    with pytest.raises(ValueError):
        await client.generate_free_agent_pitch({"team_name": "Test"})
