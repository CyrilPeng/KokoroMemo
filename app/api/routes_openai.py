"""OpenAI-compatible proxy routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.protocol_common import format_model_item, get_exposed_models
from app.pipeline.chat import ChatPipeline

router = APIRouter()


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
    return await ChatPipeline().handle(request)
