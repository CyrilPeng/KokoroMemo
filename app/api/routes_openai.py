"""OpenAI-compatible proxy routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.protocol_common import format_model_item, get_exposed_models
from app.pipeline.chat import ChatPipeline

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: Any = None  # string, list, or null (tool calls only)
    name: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None

    model_config = ConfigDict(extra="allow")


class ChatCompletionRequest(BaseModel):
    """Minimal OpenAI chat completion request shape for early validation."""

    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None

    model_config = ConfigDict(extra="allow")


@router.get("/v1/models")
async def list_models():
    exposed_models = get_exposed_models()
    return {
        "object": "list",
        "data": [format_model_item(model_id) for model_id in exposed_models],
    }


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(request: Request):
    try:
        raw_body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "请求体不是有效的 JSON", "type": "invalid_request_error"}},
        )

    try:
        ChatCompletionRequest.model_validate(raw_body)
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"error": {"message": f"请求体校验失败: {exc}", "type": "invalid_request_error"}},
        )

    return await ChatPipeline().handle(request, raw_body=raw_body)
