import httpx
import pytest

from app.services.llm import OpenRouterClient


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
    client = OpenRouterClient(api_key="test-key", model="google/gemini-2.0-flash-lite-001")
    text = await client.complete("system", "user", temperature=0.2, max_output_tokens=128)

    assert text == "Recap text"
    assert dummy_client.last_json["model"] == "google/gemini-2.0-flash-lite-001"
    assert dummy_client.last_json["temperature"] == 0.2
    assert dummy_client.last_json["max_output_tokens"] == 128
    assert dummy_client.last_json["messages"][0]["role"] == "system"
    assert dummy_client.last_headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_openrouter_missing_key_raises(monkeypatch):
    client = OpenRouterClient(api_key=None)
    with pytest.raises(RuntimeError):
        await client.complete("system", "user")
