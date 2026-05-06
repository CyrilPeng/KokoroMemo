import pytest

from app.proxy import llm_providers
from app.proxy.llm_providers import GeminiProvider, close_llm_http_client, get_llm_http_client


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "你好"}]}}]}


class FakeHttpClient:
    is_closed = False

    def __init__(self):
        self.calls = []

    async def post(self, url, *, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse()


@pytest.mark.asyncio
async def test_gemini_api_key_uses_header_not_query(monkeypatch):
    fake_client = FakeHttpClient()
    monkeypatch.setattr(llm_providers, "_shared_http_client", fake_client)

    provider = GeminiProvider("https://generativelanguage.googleapis.com/v1beta", "secret-key", "gemini-test")
    response = await provider.chat({"messages": [{"role": "user", "content": "hi"}]}, timeout=12)

    assert response["choices"][0]["message"]["content"] == "你好"
    call = fake_client.calls[0]
    assert call["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert "key=" not in call["url"]
    assert call["headers"]["x-goog-api-key"] == "secret-key"
    assert call["timeout"] == 12


@pytest.mark.asyncio
async def test_llm_http_client_is_reused_and_closable():
    await close_llm_http_client()
    first = get_llm_http_client()
    second = get_llm_http_client()
    assert first is second
    await close_llm_http_client()
    assert first.is_closed
