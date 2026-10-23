from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_admin_payload_rejects_non_object_body(async_client: AsyncClient, app_config):
    response = await async_client.post(
        "/admin/inbox/batch",
        content="[]",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_admin_payload_appears_in_openapi_schema():
    schemas = app.openapi()["components"]["schemas"]

    assert "AdminPayload" in schemas
    assert schemas["AdminPayload"].get("additionalProperties") is not False
