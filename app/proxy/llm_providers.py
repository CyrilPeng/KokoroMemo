"""LLM Provider abstraction and implementations.

Supports: OpenAI-compatible, OpenAI Responses, Anthropic, Gemini.
All providers accept OpenAI-format messages and return OpenAI-format responses.
"""

from __future__ import annotations

import json
import time
import uuid
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

logger = logging.getLogger("kokoromemo.llm_providers")


class LLMProvider(ABC):
    """Base class for LLM providers."""

    provider_name: str

    @abstractmethod
    async def chat(self, body: dict, timeout: int) -> dict:
        """Non-streaming chat. Returns OpenAI-compatible response JSON."""
        pass

    @abstractmethod
    async def stream_chat(self, body: dict, timeout: int) -> AsyncIterator[str]:
        """Streaming chat. Yields SSE lines in OpenAI format."""
        pass


def _make_openai_response(content: str, model: str, finish_reason: str = "stop") -> dict:
    """Build a standard OpenAI chat completion response."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _make_stream_chunk(content: str, model: str, finish_reason: str | None = None) -> str:
    """Build an SSE data line for streaming."""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}"


# =============================================================================
# OpenAI-Compatible Provider (Chat Completions)
# =============================================================================

class OpenAICompatibleProvider(LLMProvider):
    """Standard OpenAI Chat Completions API. Works with OpenAI, DeepSeek, Groq, etc."""

    provider_name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def chat(self, body: dict, timeout: int) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def stream_chat(self, body: dict, timeout: int) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        body["stream"] = True
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        yield line


# =============================================================================
# OpenAI Responses API Provider
# =============================================================================

class OpenAIResponsesProvider(LLMProvider):
    """OpenAI Responses API (newer endpoint)."""

    provider_name = "openai_responses"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _convert_to_responses_format(self, body: dict) -> dict:
        """Convert OpenAI chat format to Responses API format."""
        messages = body.get("messages", [])
        # Responses API uses "input" field
        input_items = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                input_items.append({"role": "system", "content": content})
            elif role == "user":
                input_items.append({"role": "user", "content": content})
            elif role == "assistant":
                input_items.append({"role": "assistant", "content": content})

        payload = {
            "model": body.get("model", self.model),
            "input": input_items,
        }
        if body.get("temperature") is not None:
            payload["temperature"] = body["temperature"]
        if body.get("max_tokens") is not None:
            payload["max_output_tokens"] = body["max_tokens"]
        return payload

    async def chat(self, body: dict, timeout: int) -> dict:
        url = f"{self.base_url}/responses"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = self._convert_to_responses_format(body)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # Extract text from Responses API format
        content = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        content += part.get("text", "")
        model = data.get("model", body.get("model", self.model))
        return _make_openai_response(content, model)

    async def stream_chat(self, body: dict, timeout: int) -> AsyncIterator[str]:
        url = f"{self.base_url}/responses"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = self._convert_to_responses_format(body)
        payload["stream"] = True

        model = body.get("model", self.model)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        yield "data: [DONE]"
                        break
                    try:
                        event = json.loads(line[6:])
                        event_type = event.get("type", "")
                        if event_type == "response.output_text.delta":
                            delta = event.get("delta", "")
                            if delta:
                                yield _make_stream_chunk(delta, model)
                        elif event_type == "response.completed":
                            yield _make_stream_chunk("", model, finish_reason="stop")
                            yield "data: [DONE]"
                    except json.JSONDecodeError:
                        pass


# =============================================================================
# Anthropic Provider (Messages API)
# =============================================================================

class AnthropicProvider(LLMProvider):
    """Anthropic Claude Messages API."""

    provider_name = "anthropic"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _convert_to_anthropic_format(self, body: dict) -> dict:
        """Convert OpenAI messages to Anthropic format."""
        messages = body.get("messages", [])
        system_text = ""
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_text += content + "\n"
            elif role == "user":
                anthropic_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                anthropic_messages.append({"role": "assistant", "content": content})

        # Anthropic requires alternating user/assistant; merge consecutive same-role
        merged = []
        for msg in anthropic_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n" + msg["content"]
            else:
                merged.append(msg)

        # Must start with user
        if merged and merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": "..."})

        payload = {
            "model": body.get("model", self.model),
            "messages": merged,
            "max_tokens": body.get("max_tokens", 4096),
        }
        if system_text.strip():
            payload["system"] = system_text.strip()
        if body.get("temperature") is not None:
            payload["temperature"] = body["temperature"]
        if body.get("top_p") is not None:
            payload["top_p"] = body["top_p"]

        return payload

    async def chat(self, body: dict, timeout: int) -> dict:
        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = self._convert_to_anthropic_format(body)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        model = data.get("model", body.get("model", self.model))
        return _make_openai_response(content, model)

    async def stream_chat(self, body: dict, timeout: int) -> AsyncIterator[str]:
        url = f"{self.base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = self._convert_to_anthropic_format(body)
        payload["stream"] = True

        model = body.get("model", self.model)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                        event_type = event.get("type", "")
                        if event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield _make_stream_chunk(text, model)
                        elif event_type == "message_stop":
                            yield _make_stream_chunk("", model, finish_reason="stop")
                            yield "data: [DONE]"
                    except json.JSONDecodeError:
                        pass


# =============================================================================
# Gemini Provider (Google AI)
# =============================================================================

class GeminiProvider(LLMProvider):
    """Google Gemini API."""

    provider_name = "gemini"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _convert_to_gemini_format(self, body: dict) -> tuple[str, dict]:
        """Convert OpenAI messages to Gemini format. Returns (url, payload)."""
        messages = body.get("messages", [])
        system_text = ""
        contents = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_text += content + "\n"
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == "assistant":
                contents.append({"role": "model", "parts": [{"text": content}]})

        model = body.get("model", self.model)
        payload: dict = {"contents": contents}

        if system_text.strip():
            payload["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}

        generation_config = {}
        if body.get("temperature") is not None:
            generation_config["temperature"] = body["temperature"]
        if body.get("max_tokens") is not None:
            generation_config["maxOutputTokens"] = body["max_tokens"]
        if body.get("top_p") is not None:
            generation_config["topP"] = body["top_p"]
        if generation_config:
            payload["generationConfig"] = generation_config

        return model, payload

    async def chat(self, body: dict, timeout: int) -> dict:
        model, payload = self._convert_to_gemini_format(body)
        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        content = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                content += part.get("text", "")

        return _make_openai_response(content, model)

    async def stream_chat(self, body: dict, timeout: int) -> AsyncIterator[str]:
        model, payload = self._convert_to_gemini_format(body)
        url = f"{self.base_url}/models/{model}:streamGenerateContent?alt=sse&key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for part in parts:
                                text = part.get("text", "")
                                if text:
                                    yield _make_stream_chunk(text, model)
                    except json.JSONDecodeError:
                        pass

        yield _make_stream_chunk("", model, finish_reason="stop")
        yield "data: [DONE]"


# =============================================================================
# Factory
# =============================================================================

def create_llm_provider(provider: str, base_url: str, api_key: str, model: str) -> LLMProvider:
    """Create an LLM provider instance based on provider type string."""
    providers = {
        "openai_compatible": OpenAICompatibleProvider,
        "openai_responses": OpenAIResponsesProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
    }
    cls = providers.get(provider)
    if not cls:
        raise ValueError(f"Unknown LLM provider: {provider}. Supported: {list(providers.keys())}")
    return cls(base_url=base_url, api_key=api_key, model=model)
