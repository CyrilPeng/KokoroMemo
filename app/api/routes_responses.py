"""OpenAI Responses-compatible inbound proxy routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.protocol_openai_family import (
    openai_to_responses,
    responses_request_to_openai,
    stream_openai_to_responses,
)
from app.pipeline.chat import ChatPipeline

router = APIRouter()


@router.post("/v1/responses")
@router.post("/responses")
async def responses(request: Request):
    raw_body = await request.json()
    openai_body = responses_request_to_openai(raw_body)
    pipeline_response = await ChatPipeline().handle(request, raw_body=openai_body)

    if isinstance(pipeline_response, StreamingResponse):
        return StreamingResponse(
            stream_openai_to_responses(pipeline_response, raw_body),
            media_type="text/event-stream",
        )

    if isinstance(pipeline_response, JSONResponse):
        payload = json.loads(pipeline_response.body.decode("utf-8"))
        if payload.get("error"):
            return JSONResponse(status_code=pipeline_response.status_code, content=payload)
        return JSONResponse(status_code=pipeline_response.status_code, content=openai_to_responses(payload, raw_body))

    return JSONResponse(
        status_code=500, content={"error": {"message": "Unexpected proxy response", "type": "proxy_error"}}
    )
