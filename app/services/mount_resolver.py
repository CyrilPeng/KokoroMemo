"""Resolve memory-library mounts from explicit, preset, and default sources."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from app.services.types import MountResolution
from app.storage.sqlite_cards import DEFAULT_MEMORY_LIBRARY_ID


class MountResolutionError(ValueError):
    """Raised when a mount reference cannot be resolved."""


def _normalize_library_ids(library_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized = [library_id for library_id in dict.fromkeys(library_ids or []) if library_id]
    return normalized or [DEFAULT_MEMORY_LIBRARY_ID]


def _normalize_write_library_id(library_ids: list[str], write_library_id: str | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if write_library_id in library_ids:
        return write_library_id or library_ids[0], warnings
    if write_library_id:
        warnings.append("write_library_not_mounted")
    return library_ids[0], warnings


class MountResolver:
    def __init__(self, memory_db_path: str, app_db_path: str | None = None) -> None:
        self.memory_db_path = memory_db_path
        self.app_db_path = app_db_path

    async def resolve_selection(self, data: dict[str, Any], *, source: str = "explicit") -> MountResolution:
        """Resolve an explicit GUI/API mount selection or a mount preset."""
        mount_preset_id = data.get("mount_preset_id")
        if mount_preset_id:
            return await self.resolve_preset(mount_preset_id, source="preset")

        library_ids = _normalize_library_ids(data.get("library_ids") or data.get("mounted_library_ids"))
        write_library_id, warnings = _normalize_write_library_id(library_ids, data.get("write_library_id"))
        return MountResolution(
            mounted_library_ids=library_ids,
            write_library_id=write_library_id,
            source=source,
            warnings=warnings,
        )

    async def resolve_preset(self, preset_id: str, *, source: str = "preset") -> MountResolution:
        from app.storage.sqlite_cards import get_mount_preset

        preset = await get_mount_preset(self.memory_db_path, preset_id)
        if not preset:
            raise MountResolutionError(f"Memory mount preset not found: {preset_id}")
        library_ids = _normalize_library_ids(json.loads(preset.get("library_ids_json") or "[]"))
        write_library_id, warnings = _normalize_write_library_id(library_ids, preset.get("write_library_id"))
        return MountResolution(
            mounted_library_ids=library_ids,
            write_library_id=write_library_id,
            source=source,
            warnings=warnings,
        )

    async def resolve_character_defaults(
        self, character_id: str, *, require_auto_apply: bool = False
    ) -> MountResolution | None:
        if not self.app_db_path:
            return None
        from app.storage.sqlite_app import get_character_defaults

        defaults = await get_character_defaults(self.app_db_path, character_id)
        if not defaults:
            return None
        if require_auto_apply and not defaults.get("auto_apply"):
            return None
        if defaults.get("mount_preset_id"):
            resolution = await self.resolve_preset(defaults["mount_preset_id"], source="character_default_preset")
            return replace(resolution, source="character_default")
        library_ids = _normalize_library_ids(defaults.get("library_ids"))
        write_library_id, warnings = _normalize_write_library_id(library_ids, defaults.get("write_library_id"))
        return MountResolution(
            mounted_library_ids=library_ids,
            write_library_id=write_library_id,
            source="character_default",
            warnings=warnings,
        )

    async def resolve_global_defaults(self) -> MountResolution | None:
        from app.storage.sqlite_state import SQLiteStateStore

        default_config = await SQLiteStateStore(self.memory_db_path).get_default_conversation_config()
        if not default_config.mount_preset_id:
            return None
        return await self.resolve_preset(default_config.mount_preset_id, source="global_default")

    async def conversation_has_custom_mounts(self, conversation_id: str) -> bool:
        from app.storage.sqlite_cards import get_conversation_mounts

        mounts = await get_conversation_mounts(self.memory_db_path, conversation_id)
        return bool(mounts and any(mount.get("library_id") != DEFAULT_MEMORY_LIBRARY_ID for mount in mounts))
