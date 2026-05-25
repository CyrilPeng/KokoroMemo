"""Anthropic-compatible inbound proxy routes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.protocol_common import format_model_item, get_exposed_models
from app.pipeline.chat import ChatPipeline

router = APIRouter()

def _normalize_anthropic_model(model_id: Any) -> Any:
    if not isinstance(model_id, str):
        return model_id
    if model_id.endswith("[1m]"):
        return model_id[:-4]
    return model_id


def _content_blocks_to_text(blocks: Any) -> str:
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "tool_result":
            content = block.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.append(_content_blocks_to_text(content))
    return "\n".join(part for part in parts if part)


def _anthropic_to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for idx, block in enumerate(content):
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type")
                    if block_type == "text" and isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                    elif block_type == "tool_use":
                        tool_calls.append(
                            {
                                "id": block.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                                "type": "function",
                                "function": {
                                    "name": block.get("name") or f"tool_{idx}",
                                    "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                                },
                            }
                        )
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": "\n".join(part for part in text_parts if part),
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            result.append(assistant_message)
            continue

        if role == "user":
            if isinstance(content, str):
                result.append({"role": "user", "content": content})
                continue
            if not isinstance(content, list):
                continue

            text_parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
                elif block_type == "tool_result":
                    if text_parts:
                        result.append({"role": "user", "content": "\n".join(text_parts)})
                        text_parts = []
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id") or "",
                            "content": _content_blocks_to_text(block.get("content")),
                        }
                    )
            if text_parts:
                result.append({"role": "user", "content": "\n".join(text_parts)})
    return result


def _anthropic_tools_to_openai(tools: Any) -> list[dict[str, Any]]:
    if not isinstance(tools, list):
        return []
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not name:
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description") or "",
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return converted


def _anthropic_request_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages", [])
    if not isinstance(messages, list):
        messages = []

    openai_messages: list[dict[str, Any]] = []
    system = body.get("system")
    if isinstance(system, str) and system.strip():
        openai_messages.append({"role": "system", "content": system.strip()})
    elif isinstance(system, list):
        system_text = _content_blocks_to_text(system).strip()
        if system_text:
            openai_messages.append({"role": "system", "content": system_text})

    openai_messages.extend(_anthropic_to_openai_messages(messages))

    payload: dict[str, Any] = {
        "model": _normalize_anthropic_model(body.get("model")),
        "messages": openai_messages,
        "stream": bool(body.get("stream")),
    }
    if body.get("max_tokens") is not None:
        payload["max_tokens"] = body.get("max_tokens")
    if body.get("temperature") is not None:
        payload["temperature"] = body.get("temperature")
    if body.get("metadata") is not None:
        payload["metadata"] = body.get("metadata")
    tools = _anthropic_tools_to_openai(body.get("tools"))
    if tools:
        payload["tools"] = tools
    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, dict):
        tool_type = tool_choice.get("type")
        if tool_type == "tool" and tool_choice.get("name"):
            payload["tool_choice"] = {"type": "function", "function": {"name": tool_choice["name"]}}
        elif tool_type in {"auto", "none", "required"}:
            payload["tool_choice"] = tool_type
    return payload


def _openai_message_to_anthropic_content(message: dict[str, Any]) -> list[dict[str, Any]]:
    content_blocks: list[dict[str, Any]] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        content_blocks.append({"type": "text", "text": content})
    tool_calls = message.get("tool_calls") or []
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            raw_arguments = function.get("arguments")
            try:
                parsed_arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) and raw_arguments else {}
            except json.JSONDecodeError:
                parsed_arguments = {}
            content_blocks.append(
                {
                    "type": "tool_use",
                    "id": tool_call.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                    "name": function.get("name") or "tool",
                    "input": parsed_arguments,
                }
            )
    return content_blocks


def _openai_response_to_anthropic(data: dict[str, Any], request_body: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices", [])
    message = choices[0].get("message", {}) if choices else {}
    content_blocks = _openai_message_to_anthropic_content(message)
    finish_reason = choices[0].get("finish_reason") if choices else None
    stop_reason = "tool_use" if message.get("tool_calls") else "end_turn"
    if finish_reason in {"length", "max_tokens"}:
        stop_reason = "max_tokens"
    usage = data.get("usage") or {}
    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": data.get("model") or request_body.get("model"),
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


async def _stream_openai_to_anthropic(openai_response: StreamingResponse, request_body: dict[str, Any]):
    message_id = f"msg_{uuid.uuid4().hex[:24]}"
    model = request_body.get("model")
    text_block_started = False
    tool_states: dict[int, dict[str, Any]] = {}

    start_payload = {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    }
    yield f"event: message_start\ndata: {json.dumps(start_payload, ensure_ascii=False)}\n\n"

    stop_reason = "end_turn"
    async for chunk in openai_response.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data: "):
                continue
            if line == "data: [DONE]":
                continue
            payload = json.loads(line[6:])
            if payload.get("error"):
                yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                return
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}

            content_delta = delta.get("content")
            if content_delta:
                if not text_block_started:
                    text_block_started = True
                    start = {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
                    yield f"event: content_block_start\ndata: {json.dumps(start, ensure_ascii=False)}\n\n"
                delta_payload = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": content_delta}}
                yield f"event: content_block_delta\ndata: {json.dumps(delta_payload, ensure_ascii=False)}\n\n"

            tool_calls = delta.get("tool_calls") or []
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                index = tool_call.get("index", 0)
                state = tool_states.setdefault(index, {"started": False, "id": None, "name": None})
                tool_id = tool_call.get("id") or state["id"] or f"toolu_{uuid.uuid4().hex[:12]}"
                function = tool_call.get("function") or {}
                tool_name = function.get("name") or state["name"] or f"tool_{index}"
                if not state["started"]:
                    state.update({"started": True, "id": tool_id, "name": tool_name})
                    start = {
                        "type": "content_block_start",
                        "index": index + 1,
                        "content_block": {"type": "tool_use", "id": tool_id, "name": tool_name, "input": {}},
                    }
                    yield f"event: content_block_start\ndata: {json.dumps(start, ensure_ascii=False)}\n\n"
                    stop_reason = "tool_use"
                arguments_delta = function.get("arguments")
                if arguments_delta:
                    delta_payload = {
                        "type": "content_block_delta",
                        "index": index + 1,
                        "delta": {"type": "input_json_delta", "partial_json": arguments_delta},
                    }
                    yield f"event: content_block_delta\ndata: {json.dumps(delta_payload, ensure_ascii=False)}\n\n"

            finish_reason = choice.get("finish_reason")
            if finish_reason in {"length", "max_tokens"}:
                stop_reason = "max_tokens"

    if text_block_started:
        stop = {"type": "content_block_stop", "index": 0}
        yield f"event: content_block_stop\ndata: {json.dumps(stop, ensure_ascii=False)}\n\n"
    for index, state in sorted(tool_states.items()):
        if state.get("started"):
            stop = {"type": "content_block_stop", "index": index + 1}
            yield f"event: content_block_stop\ndata: {json.dumps(stop, ensure_ascii=False)}\n\n"

    message_delta = {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": 0}}
    yield f"event: message_delta\ndata: {json.dumps(message_delta, ensure_ascii=False)}\n\n"
    yield "event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"


@router.get("/anthropic/v1/models")
async def list_models():
    exposed_models = get_exposed_models()
    return {
        "object": "list",
        "data": [format_model_item(model_id) for model_id in exposed_models],
    }


@router.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    raw_body = await request.json()
    openai_body = _anthropic_request_to_openai(raw_body)
    pipeline_response = await ChatPipeline().handle(request, raw_body=openai_body)

    if isinstance(pipeline_response, StreamingResponse):
        return StreamingResponse(
            _stream_openai_to_anthropic(pipeline_response, raw_body),
            media_type="text/event-stream",
        )

    if isinstance(pipeline_response, JSONResponse):
        payload = json.loads(pipeline_response.body.decode("utf-8"))
        if payload.get("error"):
            return JSONResponse(status_code=pipeline_response.status_code, content=payload)
        return JSONResponse(status_code=pipeline_response.status_code, content=_openai_response_to_anthropic(payload, raw_body))

    return JSONResponse(status_code=500, content={"error": {"message": "Unexpected proxy response", "type": "proxy_error"}})
