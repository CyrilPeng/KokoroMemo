"""Shared helpers for parsing model JSON output."""

from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(text: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Parse a JSON object from a model response, tolerating ```json fences and
    trailing commentary. Returns ``fallback`` (or ``{}``) when parsing fails
    or the result is not an object.
    """
    fallback_value = fallback if fallback is not None else {}
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return dict(fallback_value)
    if isinstance(payload, dict):
        return payload
    return dict(fallback_value)


def safe_float(value: Any, fallback: float) -> float:
    """Best-effort float coercion; returns ``fallback`` on any failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
