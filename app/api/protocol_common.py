"""Shared helpers for protocol compatibility routes."""

from __future__ import annotations

from app.core.state import get_config


def format_model_item(model_id: str) -> dict:
    return {
        "id": model_id,
        "object": "model",
        "created": 0,
        "owned_by": "kokoromemo",
    }


def get_exposed_models() -> list[str]:
    cfg = get_config()
    exposed_models = [model for model in cfg.compatibility.exposed_models if model]
    if not exposed_models:
        exposed_models = [cfg.llm.model] if cfg.llm.model else []
    return exposed_models
