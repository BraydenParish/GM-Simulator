import httpx
import pytest

from app.services.llm import (
    DEFAULT_FALLBACK_MODELS,
    DEFAULT_MODEL,
    LLMResponse,
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
