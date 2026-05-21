"""OpenAI-compatible proxy routes."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request

from app.core.state import get_config
from app.pipeline.chat import ChatPipeline

router = APIRouter()


@router.get("/v1/models")
async def list_models():
    cfg = get_config()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{cfg.llm.base_url}/models",
                headers={"Authorization": f"Bearer {cfg.llm.get_api_key()}"},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {
        "object": "list",
        "data": [{"id": cfg.llm.model, "object": "model", "created": 0, "owned_by": "kokoromemo"}],
    }


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(request: Request):
    return await ChatPipeline().handle(request)
