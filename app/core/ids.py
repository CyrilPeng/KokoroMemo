"""ID generation utilities."""

from __future__ import annotations

import re
import time
import uuid


def generate_id(prefix: str = "") -> str:
    """Generate a short unique ID with optional prefix."""
    ts = int(time.time() * 1000) % 0xFFFFFFFF
    suffix = uuid.uuid4().hex[:8]
    id_str = f"{prefix}{ts:08x}_{suffix}" if prefix else f"{ts:08x}_{suffix}"
    return id_str


def sanitize_id(raw: str) -> str:
    """Sanitize a string to be a safe ID: lowercase, alphanumeric, underscore, dash."""
    s = raw.lower().strip()
    s = re.sub(r"[^a-z0-9_\-]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:64]
