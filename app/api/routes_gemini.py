"""Gemini-compatible inbound proxy routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.protocol_common import get_exposed_models
from app.pipeline.chat import ChatPipeline

router = APIRouter()


def _parts_to_text(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunk for chunk in chunks if chunk)


def _gemini_request_to_openai(model: str, body: dict[str, Any], stream: bool) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    system_instruction = body.get("systemInstruction")
    if isinstance(system_instruction, dict):
        system_text = _parts_to_text(system_instruction.get("parts"))
        if system_text:
            messages.append({"role": "system", "content": system_text})

    contents = body.get("contents", [])
    if isinstance(contents, list):
        for item in contents:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            text = _parts_to_text(item.get("parts"))
            if not text:
                continue
            if role == "model":
                messages.append({"role": "assistant", "content": text})
            else:
                messages.append({"role": "user", "content": text})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    generation_config = body.get("generationConfig")
    if isinstance(generation_config, dict):
        if generation_config.get("temperature") is not None:
            payload["temperature"] = generation_config["temperature"]
        if generation_config.get("maxOutputTokens") is not None:
            payload["max_tokens"] = generation_config["maxOutputTokens"]
        if generation_config.get("topP") is not None:
            payload["top_p"] = generation_config["topP"]
    return payload


def _openai_to_gemini(data: dict[str, Any], model: str) -> dict[str, Any]:
    choices = data.get("choices", [])
    message = choices[0].get("message", {}) if choices else {}
    content = message.get("content") or ""
    finish_reason = choices[0].get("finish_reason") if choices else "STOP"
    usage = data.get("usage") or {}
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": content}]},
                "finishReason": str(finish_reason).upper(),
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": usage.get("prompt_tokens", 0),
            "candidatesTokenCount": usage.get("completion_tokens", 0),
            "totalTokenCount": usage.get("total_tokens", 0),
        },
        "modelVersion": model,
    }


async def _stream_openai_to_gemini(openai_response: StreamingResponse, model: str):
    async for chunk in openai_response.body_iterator:
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data: "):
                continue
            if line == "data: [DONE]":
                return
            payload = json.loads(line[6:])
            if payload.get("error"):
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                return
            choice = (payload.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            content = delta.get("content")
            finish_reason = choice.get("finish_reason")
            if content or finish_reason:
                gemini_chunk = {
                    "candidates": [
                        {
                            "content": {"role": "model", "parts": ([{"text": content}] if content else [])},
                            "finishReason": str(finish_reason).upper() if finish_reason else None,
                            "index": 0,
                        }
                    ],
                    "modelVersion": model,
                }
                yield f"data: {json.dumps(gemini_chunk, ensure_ascii=False)}\n\n"


@router.get("/v1beta/models")
async def list_models():
    return {
        "models": [
            {
                "name": f"models/{model_id}",
                "displayName": model_id,
                "description": "KokoroMemo compatibility model",
            }
            for model_id in get_exposed_models()
        ]
    }


@router.post("/v1beta/models/{model}:generateContent")
@router.post("/v1/models/{model}:generateContent")
async def generate_content(model: str, request: Request):
    raw_body = await request.json()
    openai_body = _gemini_request_to_openai(model, raw_body, stream=False)
    pipeline_response = await ChatPipeline().handle(request, raw_body=openai_body)
    if isinstance(pipeline_response, JSONResponse):
        payload = json.loads(pipeline_response.body.decode("utf-8"))
        if payload.get("error"):
            return JSONResponse(status_code=pipeline_response.status_code, content=payload)
        return JSONResponse(status_code=pipeline_response.status_code, content=_openai_to_gemini(payload, model))
    return JSONResponse(
        status_code=500, content={"error": {"message": "Unexpected proxy response", "type": "proxy_error"}}
    )


@router.post("/v1beta/models/{model}:streamGenerateContent")
@router.post("/v1/models/{model}:streamGenerateContent")
async def stream_generate_content(model: str, request: Request):
    raw_body = await request.json()
    openai_body = _gemini_request_to_openai(model, raw_body, stream=True)
    pipeline_response = await ChatPipeline().handle(request, raw_body=openai_body)
    if isinstance(pipeline_response, StreamingResponse):
        return StreamingResponse(
            _stream_openai_to_gemini(pipeline_response, model),
            media_type="text/event-stream",
        )
    if isinstance(pipeline_response, JSONResponse):
        payload = json.loads(pipeline_response.body.decode("utf-8"))
        if payload.get("error"):
            return JSONResponse(status_code=pipeline_response.status_code, content=payload)
        return JSONResponse(status_code=pipeline_response.status_code, content=_openai_to_gemini(payload, model))
    return JSONResponse(
        status_code=500, content={"error": {"message": "Unexpected proxy response", "type": "proxy_error"}}
    )
