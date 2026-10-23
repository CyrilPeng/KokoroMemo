"""Shared Pydantic request boundary for admin endpoints."""

from __future__ import annotations

from app.core.pydantic_compat import CompatBaseModel


class AdminPayload(CompatBaseModel):
    """Flexible admin request body.

    Extra keys are intentionally preserved while the admin API is migrated from
    raw dictionaries to explicit request models. Routes can promote stable keys
    to typed fields without breaking existing clients.
    """
