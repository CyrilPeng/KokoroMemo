"""Admin API sub-package — splits routes_admin.py into domain-based modules."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.admin._helpers import _require_admin, _resolve_mount_selection
from app.api.admin.airp import router as airp_router
from app.api.admin.characters import router as characters_router
from app.api.admin.conversation_profiles import router as conversation_profiles_router
from app.api.admin.conversations import router as conversations_router
from app.api.admin.import_routes import router as import_router
from app.api.admin.inbox import router as inbox_router
from app.api.admin.libraries import router as libraries_router
from app.api.admin.memories import router as memories_router
from app.api.admin.state import router as state_router
from app.api.admin.system import router as system_router

router = APIRouter()

for sub in [
    system_router,
    airp_router,
    conversation_profiles_router,
    conversations_router,
    characters_router,
    memories_router,
    inbox_router,
    state_router,
    libraries_router,
    import_router,
]:
    router.include_router(sub)

__all__ = ["router", "_require_admin", "_resolve_mount_selection"]
