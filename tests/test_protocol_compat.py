"""Regression tests for protocol compatibility routes."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.state import set_config
from app.main import app
from tests.test_regression import FakeChatProvider, cleanup_test_dir, configure_app, make_test_dir


@pytest.mark.asyncio
async def test_anthropic_messages_converts_tool_use(monkeypatch):
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        set_config(cfg)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/anthropic/v1/messages",
                json={
                    "model": "fake-model[1m]",
                    "max_tokens": 64,
                    "tools": [
                        {
                            "name": "lookup_weather",
                            "description": "Look up weather",
                            "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
                        }
                    ],
                    "messages": [{"role": "user", "content": [{"type": "text", "text": "Weather?"}]}],
                },
            )

        assert resp.status_code == 200
        assert FakeChatProvider.captured_bodies[-1]["model"] == "fake-model"
        assert FakeChatProvider.captured_bodies[-1]["tools"][0]["function"]["name"] == "lookup_weather"
        assert resp.json()["type"] == "message"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_responses_endpoint_converts_to_chat_completion(monkeypatch):
    test_dir = make_test_dir()
    try:
        configure_app(test_dir)
        provider = FakeChatProvider()
        FakeChatProvider.captured_bodies.clear()
        monkeypatch.setattr("app.proxy.llm_providers.create_llm_provider", lambda **kwargs: provider)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/responses",
                json={
                    "model": "fake-model",
                    "input": [{"role": "user", "content": [{"type": "input_text", "text": "Reply OK"}]}],
                    "max_output_tokens": 32,
                },
            )

        assert resp.status_code == 200
        assert FakeChatProvider.captured_bodies[-1]["messages"] == [{"role": "user", "content": "Reply OK"}]
        data = resp.json()
        assert data["object"] == "response"
        assert data["output"][0]["content"][0]["type"] == "output_text"
    finally:
        cleanup_test_dir(test_dir)


@pytest.mark.asyncio
async def test_gemini_models_endpoint_uses_configured_exposed_models():
    test_dir = make_test_dir()
    try:
        cfg = configure_app(test_dir)
        cfg.compatibility.exposed_models = ["model-b", "model-a"]
        set_config(cfg)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1beta/models")

        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()["models"]]
        assert names == ["models/model-b", "models/model-a"]
    finally:
        cleanup_test_dir(test_dir)
