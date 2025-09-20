import httpx
import pytest

from app.services.llm import (
    DEFAULT_FALLBACK_MODEL,
    DEFAULT_MODEL,
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
                ]
            }
        )


@pytest.mark.asyncio
async def test_openrouter_client_builds_payload(monkeypatch):
    dummy_client = DummyAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: dummy_client)
    client = OpenRouterClient(api_key="test-key", model=DEFAULT_MODEL)
    text = await client.complete("system", "user", temperature=0.2, max_output_tokens=128)

    assert text == "Recap text"
    assert dummy_client.last_json["model"] == DEFAULT_MODEL
    assert dummy_client.last_json["temperature"] == 0.2
    assert dummy_client.last_json["max_output_tokens"] == 128
    assert dummy_client.last_json["messages"][0]["role"] == "system"
    assert dummy_client.last_headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_openrouter_missing_key_raises(monkeypatch):
    client = OpenRouterClient(api_key=None)
    with pytest.raises(RuntimeError):
        await client.complete("system", "user")


class DummyHTTPError(httpx.HTTPStatusError):
    def __init__(self) -> None:
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(503, request=request)
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
                ]
            }
        )


@pytest.mark.asyncio
async def test_openrouter_falls_back_to_secondary_model(monkeypatch):
    dummy_client = DummyFailThenSucceedClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: dummy_client)
    client = OpenRouterClient(
        api_key="key", model=DEFAULT_MODEL, fallback_model=DEFAULT_FALLBACK_MODEL
    )

    text = await client.complete("sys", "user")

    assert dummy_client.attempts == 2
    assert dummy_client.last_models == [DEFAULT_MODEL, DEFAULT_FALLBACK_MODEL]
    assert text == f"response from {DEFAULT_FALLBACK_MODEL}"


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
    client = OpenRouterClient(api_key="key", model="model-a", fallback_model="model-b")

    with pytest.raises(RuntimeError) as exc:
        await client.complete("sys", "user")

    assert "failed for all" in str(exc.value)
