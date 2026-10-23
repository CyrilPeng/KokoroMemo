"""OpenAI-compatible proxy routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from app.api.protocol_common import format_model_item, get_exposed_models
from app.core.pydantic_compat import CompatBaseModel, validate_model
from app.pipeline.chat import ChatPipeline

router = APIRouter()


class ChatMessage(CompatBaseModel):
    role: str
    content: Any = None  # string, list, or null (tool calls only)
    name: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None


class ChatCompletionRequest(CompatBaseModel):
    """Minimal OpenAI chat completion request shape for early validation."""

    messages: list[ChatMessage] = Field(...)
    model: str | None = None
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


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

    if not isinstance(raw_body.get("messages"), list) or not raw_body["messages"]:
        return JSONResponse(
            status_code=422,
            content={"error": {"message": "请求体必须包含至少一条 messages", "type": "invalid_request_error"}},
        )

    try:
        validate_model(ChatCompletionRequest, raw_body)
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"error": {"message": f"请求体校验失败: {exc}", "type": "invalid_request_error"}},
        )

    return await ChatPipeline().handle(request, raw_body=raw_body)
