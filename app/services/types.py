"""Shared service-layer value objects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MountResolution:
    mounted_library_ids: list[str]
    write_library_id: str
    source: str
    warnings: list[str] = field(default_factory=list)

