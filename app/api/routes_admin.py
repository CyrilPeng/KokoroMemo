"""Health check and admin routes — thin re-export after modular split.

The original monolithic routes_admin.py has been decomposed into domain-based
sub-modules under ``app.api.admin/``. All admin routes are aggregated there and
re-exported through this shim so that existing imports such as::

    from app.api.routes_admin import router
    from app.api.routes_admin import _require_admin

continue to work unchanged.
"""

from __future__ import annotations

from app.api.admin import router  # noqa: F401
from app.api.admin._helpers import _is_loopback, _require_admin  # noqa: F401

__all__ = ["router", "_require_admin", "_is_loopback"]
