from pathlib import Path
from uuid import uuid4

import pytest

from app.services.mount_resolver import MountResolutionError, MountResolver
from app.storage.sqlite_app import init_app_db, set_character_defaults
from app.storage.sqlite_cards import (
    create_memory_library,
    create_mount_preset,
    set_conversation_mounts,
)
from app.storage.sqlite_state import SQLiteStateStore


def _db_paths() -> tuple[str, str]:
    root = Path(__file__).resolve().parent.parent / ".test_dbs" / f"mount_resolver_{uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "app.sqlite"), str(root / "memory.sqlite")


@pytest.mark.asyncio
async def test_resolve_selection_prefers_mount_preset() -> None:
    _app_db, memory_db = _db_paths()
    lib_id = await create_memory_library(memory_db, "剧情库", "")
    preset_id = await create_mount_preset(
        memory_db,
        "剧情挂载",
        ["lib_default", lib_id],
        write_library_id=lib_id,
    )

    resolved = await MountResolver(memory_db).resolve_selection(
        {
            "mount_preset_id": preset_id,
            "library_ids": ["lib_default"],
            "write_library_id": "lib_default",
        }
    )

    assert resolved.mounted_library_ids == ["lib_default", lib_id]
    assert resolved.write_library_id == lib_id
    assert resolved.source == "preset"


@pytest.mark.asyncio
async def test_resolve_selection_falls_back_when_write_library_is_not_mounted() -> None:
    _app_db, memory_db = _db_paths()
    resolved = await MountResolver(memory_db).resolve_selection(
        {
            "library_ids": ["lib_default"],
            "write_library_id": "missing_lib",
        }
    )

    assert resolved.mounted_library_ids == ["lib_default"]
    assert resolved.write_library_id == "lib_default"
    assert "write_library_not_mounted" in resolved.warnings


@pytest.mark.asyncio
async def test_resolve_character_defaults_expands_preset() -> None:
    app_db, memory_db = _db_paths()
    await init_app_db(app_db)
    lib_id = await create_memory_library(memory_db, "角色库", "")
    preset_id = await create_mount_preset(
        memory_db,
        "角色挂载",
        ["lib_default", lib_id],
        write_library_id=lib_id,
    )
    await set_character_defaults(
        app_db,
        "char_a",
        mount_preset_id=preset_id,
        library_ids=["lib_default"],
        write_library_id="lib_default",
        auto_apply=True,
    )

    resolved = await MountResolver(memory_db, app_db).resolve_character_defaults("char_a", require_auto_apply=True)

    assert resolved is not None
    assert resolved.mounted_library_ids == ["lib_default", lib_id]
    assert resolved.write_library_id == lib_id
    assert resolved.source == "character_default"


@pytest.mark.asyncio
async def test_resolve_global_defaults_uses_default_config_preset() -> None:
    _app_db, memory_db = _db_paths()
    lib_id = await create_memory_library(memory_db, "全局库", "")
    preset_id = await create_mount_preset(
        memory_db,
        "全局挂载",
        ["lib_default", lib_id],
        write_library_id=lib_id,
    )
    store = SQLiteStateStore(memory_db)
    default_config = await store.get_default_conversation_config()
    payload = default_config.to_dict()
    payload["mount_preset_id"] = preset_id
    await store.set_default_conversation_config(payload)

    resolved = await MountResolver(memory_db).resolve_global_defaults()

    assert resolved is not None
    assert resolved.mounted_library_ids == ["lib_default", lib_id]
    assert resolved.write_library_id == lib_id
    assert resolved.source == "global_default"


@pytest.mark.asyncio
async def test_conversation_has_custom_mounts_ignores_default_only_mount() -> None:
    _app_db, memory_db = _db_paths()
    resolver = MountResolver(memory_db)

    assert await resolver.conversation_has_custom_mounts("new_conv") is False

    lib_id = await create_memory_library(memory_db, "自定义库", "")
    await set_conversation_mounts(memory_db, "new_conv", ["lib_default", lib_id], write_library_id=lib_id)

    assert await resolver.conversation_has_custom_mounts("new_conv") is True


@pytest.mark.asyncio
async def test_missing_preset_raises_resolution_error() -> None:
    _app_db, memory_db = _db_paths()

    with pytest.raises(MountResolutionError):
        await MountResolver(memory_db).resolve_selection({"mount_preset_id": "missing_preset"})
