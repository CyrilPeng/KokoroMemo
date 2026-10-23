from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.degradation import (
    get_degradation_snapshot,
    record_degradation,
    reset_degradation_records,
)


def test_degradation_registry_aggregates_and_redacts_context():
    reset_degradation_records()

    record_degradation("memory.retrieval", "timeout", conversation_id="conv1", api_key="secret")
    record_degradation(
        "memory.retrieval",
        RuntimeError("boom"),
        conversation_id="conv2",
        authorization="Bearer secret",
    )

    snapshot = get_degradation_snapshot()
    assert snapshot["total_events"] == 2
    assert snapshot["channel_count"] == 1
    channel = snapshot["channels"][0]
    assert channel["channel"] == "memory.retrieval"
    assert channel["count"] == 2
    assert channel["last_error"] == "boom"
    assert channel["last_context"]["conversation_id"] == "conv2"
    assert channel["last_context"]["authorization"] == "[redacted]"


@pytest.mark.asyncio
async def test_degradation_status_endpoint(async_client: AsyncClient, app_config):
    reset_degradation_records()
    record_degradation("vector_sync.worker", "temporary failure")

    response = await async_client.get("/admin/degradation-status")

    assert response.status_code == 200
    data = response.json()
    assert data["total_events"] == 1
    assert data["channels"][0]["channel"] == "vector_sync.worker"
    reset_degradation_records()


def test_degradation_registry_is_bounded(monkeypatch):
    import app.core.degradation as degradation

    reset_degradation_records()
    monkeypatch.setattr(degradation, "_MAX_CHANNELS", 2)
    record_degradation("a", "one")
    record_degradation("b", "two")
    record_degradation("c", "three")

    snapshot = get_degradation_snapshot()
    assert snapshot["channel_count"] == 2
    assert {item["channel"] for item in snapshot["channels"]} == {"a", "b"}
    reset_degradation_records()
