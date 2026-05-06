"""Configuration view shared by state board fillers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StateFillerConfigView:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 30
    temperature: float = 0.0
    min_confidence: float = 0.55
    prompt: str = ""
