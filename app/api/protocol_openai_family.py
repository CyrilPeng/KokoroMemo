"""Shared helpers for OpenAI-family inbound routes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.responses import StreamingResponse


def item_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"input_text", "output_text", "text"} and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(part for part in parts if part)


def responses_input_to_openai_messages(input_items: Any) -> list[dict[str, Any]]:
    if isinstance(input_items, str):
        return [{"role": "user", "content": input_items}]
    if not isinstance(input_items, list):
        return []

    messages: list[dict[str, Any]] = []
    for item in input_items:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "user")
        content = item_text(item.get("content"))
        if not content:
            continue
        if role not in {"system", "user", "assistant"}:
            role = "user"
        messages.append({"role": role, "content": content})
    return messages


def responses_request_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": body.get("model"),
        "messages": responses_input_to_openai_messages(body.get("input")),
        "stream": bool(body.get("stream")),
    }
    if body.get("temperature") is not None:
        payload["temperature"] = body["temperature"]
    if body.get("max_output_tokens") is not None:
        payload["max_tokens"] = body["max_output_tokens"]
    if body.get("metadata") is not None:
        payload["metadata"] = body["metadata"]
    return payload


def openai_to_responses(data: dict[str, Any], request_body: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices", [])
    message = choices[0].get("message", {}) if choices else {}
    content = message.get("content") or ""
    usage = data.get("usage") or {}
    return {
        "id": f"resp_{uuid.uuid4().hex[:24]}",
        "object": "response",
        "created_at": data.get("created"),
        "model": data.get("model") or request_body.get("model"),
        "output": [
            {
                "id": f"msg_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": content, "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


async def stream_openai_to_responses(openai_response: StreamingResponse, request_body: dict[str, Any]):
    response_id = f"resp_{uuid.uuid4().hex[:24]}"
    model = request_body.get("model")
    yield f"data: {json.dumps({'type': 'response.created', 'response': {'id': response_id, 'object': 'response', 'model': model}}, ensure_ascii=False)}\n\n"

    async for chunk in openai_response.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data: "):
                continue
            if line == "data: [DONE]":
                yield "data: [DONE]\n\n"
                return
            payload = json.loads(line[6:])
            if payload.get("error"):
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                return
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                yield f"data: {json.dumps({'type': 'response.output_text.delta', 'delta': content}, ensure_ascii=False)}\n\n"
            finish_reason = choice.get("finish_reason")
            if finish_reason:
                yield f"data: {json.dumps({'type': 'response.completed', 'response': {'id': response_id, 'object': 'response', 'model': model}}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
