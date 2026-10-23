"""Shared helpers for admin API sub-modules."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from functools import wraps
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel

from app.api.admin.schemas import AdminPayload  # noqa: F401  # resolved by FastAPI from wrapper globals
from app.core.pydantic_compat import dump_model

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_loopback(client_host: str | None) -> bool:
    if not client_host:
        return False
    return client_host in _LOOPBACK_HOSTS


def _require_admin(request: Request) -> None:
    """Require Bearer token only when ADMIN_TOKEN/admin_token is configured.

    Additional safeguard: when admin_token is empty AND the request comes from a non-loopback
    client, refuse access unless `server.allow_remote_access` is explicitly enabled. This
    prevents accidental data exposure when the GUI binds to 0.0.0.0 without setting a token.
    """
    from app.core.state import get_config

    cfg = get_config()
    token = cfg.server.get_admin_token()
    client_host = request.client.host if request.client else None
    if not token:
        if not _is_loopback(client_host) and not cfg.server.allow_remote_access:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Admin endpoint refused: no admin_token configured and remote access "
                    "not explicitly allowed (set server.allow_remote_access=true or "
                    "configure ADMIN_TOKEN)."
                ),
            )
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def body_as_dict(func: Callable[..., Any]) -> Callable[..., Any]:
    """Convert a Pydantic admin body into a dict for existing handlers."""

    parameter_names = list(inspect.signature(func).parameters)
    data_index = parameter_names.index("data") if "data" in parameter_names else None

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if data_index is not None:
            if data_index < len(args):
                value = args[data_index]
                if isinstance(value, BaseModel):
                    args = (*args[:data_index], dump_model(value), *args[data_index + 1 :])
                elif value is None:
                    args = (*args[:data_index], {}, *args[data_index + 1 :])
            elif "data" in kwargs:
                value = kwargs["data"]
                if isinstance(value, BaseModel):
                    kwargs["data"] = dump_model(value)
                elif value is None:
                    kwargs["data"] = {}
            else:
                kwargs["data"] = {}
        return await func(*args, **kwargs)

    return wrapper


async def _resolve_mount_selection(db_path: str, data: dict) -> tuple[list[str], str | None]:
    """Resolve explicit library selection or a mount preset into concrete mounts."""
    from app.services.mount_resolver import MountResolutionError, MountResolver

    try:
        resolved = await MountResolver(db_path).resolve_selection(data)
    except MountResolutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return resolved.mounted_library_ids, resolved.write_library_id
