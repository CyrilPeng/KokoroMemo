"""Shared Pydantic request boundary for admin endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AdminPayload(BaseModel):
    """Flexible admin request body.

    Extra keys are intentionally preserved while the admin API is migrated from
    raw dictionaries to explicit request models. Routes can promote stable keys
    to typed fields without breaking existing clients.
    """

    model_config = ConfigDict(extra="allow")
