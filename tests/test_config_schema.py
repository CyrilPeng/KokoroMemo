from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config_schema import DEPRECATED_CONFIG_FIELDS, get_config_schema
from app.main import app


def test_config_schema_has_unique_paths_and_deprecations():
    schema = get_config_schema()
    paths = [field["path"] for field in schema["fields"]]

    assert len(paths) == len(set(paths))
    assert set(schema["deprecated"]) == set(DEPRECATED_CONFIG_FIELDS)
    assert "storage.vector_store" in paths
    assert "memory.final_top_k" in paths


@pytest.mark.asyncio
async def test_config_schema_endpoint_reports_deprecated_fields(async_client: AsyncClient, app_config):
    response = await async_client.get("/admin/config-schema")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 1
    assert set(data["deprecated"]) == set(DEPRECATED_CONFIG_FIELDS)
    assert all(field["deprecation_reason"] for field in data["fields"] if field["deprecated"])


@pytest.mark.asyncio
async def test_admin_config_hides_deprecated_fields(app_config):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/config")

    assert response.status_code == 200
    data = response.json()
    assert data["storage"]["vector_store"] == app_config.storage.vector_store
    assert "extract_after_each_turn" not in data["memory"]["extraction"]
    assert "fallback_rule_based" not in data["memory"]["extraction"]
    assert "inject_always" not in data["memory"]["hot_context"]
    assert "detect_system_prompt_change" not in data["conversation"]
