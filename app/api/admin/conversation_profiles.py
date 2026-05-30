"""Conversation profile and default routes."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from app.api.admin._helpers import _require_admin

router = APIRouter()


@router.get("/admin/conversation-profiles")
async def list_conversation_profiles_api(request: Request):
    """List built-in and custom conversation policy profiles."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.conversation_policy import list_profiles
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    items = [{**profile.to_dict(), "is_builtin": True} for profile in list_profiles()]
    items.extend({**profile.to_dict(), "is_builtin": False} for profile in await store.list_custom_conversation_profiles())
    return {"items": items}


@router.get("/admin/retrieval-profiles")
async def list_retrieval_profiles_api(request: Request):
    """List built-in long-term memory retrieval strategy profiles."""
    _require_admin(request)
    from app.memory.conversation_policy import list_retrieval_profiles

    return {"items": [profile.to_dict() for profile in list_retrieval_profiles()]}


@router.post("/admin/conversation-profiles")
async def create_conversation_profile_api(request: Request, data: dict = Body(...)):
    """Create a custom conversation policy profile."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    profile = await SQLiteStateStore(get_config().storage.sqlite.memory_db).upsert_custom_conversation_profile(data)
    return {"status": "ok", "profile": {**profile.to_dict(), "is_builtin": False}}


@router.put("/admin/conversation-profiles/{profile_id}")
async def update_conversation_profile_api(profile_id: str, request: Request, data: dict = Body(...)):
    """Update a custom conversation policy profile."""
    _require_admin(request)
    from app.memory.conversation_policy import BUILTIN_CONVERSATION_PROFILES
    if profile_id in BUILTIN_CONVERSATION_PROFILES:
        raise HTTPException(status_code=400, detail="Built-in profiles cannot be modified")
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    payload = dict(data)
    payload["profile_id"] = profile_id
    profile = await SQLiteStateStore(get_config().storage.sqlite.memory_db).upsert_custom_conversation_profile(payload)
    return {"status": "ok", "profile": {**profile.to_dict(), "is_builtin": False}}


@router.delete("/admin/conversation-profiles/{profile_id}")
async def delete_conversation_profile_api(profile_id: str, request: Request):
    """Delete a custom conversation policy profile."""
    _require_admin(request)
    from app.memory.conversation_policy import BUILTIN_CONVERSATION_PROFILES
    if profile_id in BUILTIN_CONVERSATION_PROFILES:
        raise HTTPException(status_code=400, detail="Built-in profiles cannot be deleted")
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    ok = await SQLiteStateStore(get_config().storage.sqlite.memory_db).delete_custom_conversation_profile(profile_id)
    return {"status": "ok" if ok else "error", "message": None if ok else "custom profile not found"}


@router.get("/admin/conversation-defaults")
async def get_conversation_defaults_api(request: Request):
    """Get default policy for newly seen conversations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    return await store.get_default_conversation_config()


@router.put("/admin/conversation-defaults")
async def update_conversation_defaults_api(request: Request, data: dict = Body(...)):
    """Update default policy for newly seen conversations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    config = await store.set_default_conversation_config(data)
    return {"status": "ok", "config": config.to_dict()}
