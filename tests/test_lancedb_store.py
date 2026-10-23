from __future__ import annotations

import pytest

pytest.importorskip("lancedb")


def _vector_row(memory_id: str, library_id: str, user_id: str, vector: list[float]) -> dict:
    return {
        "memory_id": memory_id,
        "library_id": library_id,
        "user_id": user_id,
        "character_id": "",
        "conversation_id": "",
        "scope": "global",
        "memory_type": "preference",
        "content": f"memory {memory_id}",
        "summary": "",
        "tags_json": "",
        "importance": 0.8,
        "confidence": 0.9,
        "status": "active",
        "created_at": "2026-01-01 00:00:00",
        "updated_at": "2026-01-01 00:00:00",
        "embedding_model": "test",
        "vector": vector,
    }


def test_lancedb_filtered_search_and_staging_promotion(tmp_path):
    from app.storage.lancedb_store import LanceDBStore

    store = LanceDBStore(str(tmp_path / "lancedb"), table_name="memories", dimension=2)
    store.connect()
    store.upsert(
        [
            _vector_row("card_own", "lib_default", "u1", [1.0, 0.0]),
            _vector_row("card_other", "lib_other", "u1", [0.9, 0.1]),
        ]
    )

    results = store.search(
        [1.0, 0.0],
        where="status = 'active' AND user_id = 'u1' AND library_id = 'lib_default'",
        top_k=5,
    )
    assert [row["memory_id"] for row in results] == ["card_own"]

    store.create_staging_table("memories_staging")
    store.upsert_into("memories_staging", [_vector_row("card_rebuilt", "lib_default", "u1", [0.0, 1.0])])
    store.promote_staging("memories_staging")

    assert store.count() == 1
    results = store.search([0.0, 1.0], top_k=5)
    assert [row["memory_id"] for row in results] == ["card_rebuilt"]
