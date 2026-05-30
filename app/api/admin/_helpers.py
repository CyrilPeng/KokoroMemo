"""Shared helpers for admin API sub-modules."""

from __future__ import annotations

from fastapi import HTTPException, Request

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


async def _resolve_mount_selection(db_path: str, data: dict) -> tuple[list[str], str | None]:
    """Resolve explicit library selection or a mount preset into concrete mounts."""
    from app.services.mount_resolver import MountResolutionError, MountResolver

    try:
        resolved = await MountResolver(db_path).resolve_selection(data)
    except MountResolutionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return resolved.mounted_library_ids, resolved.write_library_id
