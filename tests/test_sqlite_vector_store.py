"""Tests for SqliteVectorStore — the numpy-based fallback for LanceDB."""

import os
import tempfile

import numpy as np
import pytest

from app.storage.sqlite_vector_store import SqliteVectorStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_vectors.sqlite")
        s = SqliteVectorStore(db_path=db_path, table_name="memories", dimension=4)
        s.connect()
        yield s
        if s._conn:
            s._conn.close()
            s._conn = None


def _make_row(memory_id: str, vec: list[float], **kwargs) -> dict:
    base = {
        "memory_id": memory_id,
        "library_id": "lib_default",
        "user_id": "user1",
        "character_id": "char1",
        "conversation_id": "conv1",
        "scope": "global",
        "memory_type": "preference",
        "content": f"content for {memory_id}",
        "summary": "",
        "tags_json": "[]",
        "importance": 0.5,
        "confidence": 0.8,
        "status": "approved",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "embedding_model": "test",
        "vector": vec,
    }
    base.update(kwargs)
    return base


def test_upsert_and_search(store: SqliteVectorStore):
    rows = [
        _make_row("m1", [1.0, 0.0, 0.0, 0.0]),
        _make_row("m2", [0.0, 1.0, 0.0, 0.0]),
        _make_row("m3", [0.7, 0.7, 0.0, 0.0]),
    ]
    store.upsert(rows)
    assert store.count() == 3

    results = store.search([1.0, 0.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["memory_id"] == "m1"
    assert results[0]["_distance"] < 0.01


def test_upsert_updates_existing(store: SqliteVectorStore):
    store.upsert([_make_row("m1", [1.0, 0.0, 0.0, 0.0], content="old")])
    store.upsert([_make_row("m1", [0.0, 1.0, 0.0, 0.0], content="new")])
    assert store.count() == 1
    results = store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert results[0]["content"] == "new"


def test_where_filter_equality(store: SqliteVectorStore):
    store.upsert([
        _make_row("m1", [1.0, 0.0, 0.0, 0.0], scope="global"),
        _make_row("m2", [0.9, 0.1, 0.0, 0.0], scope="character"),
    ])
    results = store.search([1.0, 0.0, 0.0, 0.0], where="scope = 'character'", top_k=10)
    assert len(results) == 1
    assert results[0]["memory_id"] == "m2"


def test_where_filter_in(store: SqliteVectorStore):
    store.upsert([
        _make_row("m1", [1.0, 0.0, 0.0, 0.0], library_id="lib_a"),
        _make_row("m2", [0.9, 0.1, 0.0, 0.0], library_id="lib_b"),
        _make_row("m3", [0.8, 0.2, 0.0, 0.0], library_id="lib_c"),
    ])
    results = store.search(
        [1.0, 0.0, 0.0, 0.0],
        where="library_id IN ('lib_a', 'lib_c')",
        top_k=10,
    )
    assert len(results) == 2
    ids = {r["memory_id"] for r in results}
    assert ids == {"m1", "m3"}


def test_where_filter_and_or(store: SqliteVectorStore):
    store.upsert([
        _make_row("m1", [1.0, 0.0, 0.0, 0.0], scope="global", status="approved"),
        _make_row("m2", [0.9, 0.1, 0.0, 0.0], scope="character", status="approved"),
        _make_row("m3", [0.8, 0.2, 0.0, 0.0], scope="character", status="pending"),
    ])
    results = store.search(
        [1.0, 0.0, 0.0, 0.0],
        where="status = 'approved' AND (scope = 'global' OR scope = 'character')",
        top_k=10,
    )
    assert len(results) == 2


def test_delete_and_count(store: SqliteVectorStore):
    store.upsert([
        _make_row("m1", [1.0, 0.0, 0.0, 0.0]),
        _make_row("m2", [0.0, 1.0, 0.0, 0.0]),
    ])
    assert store.count() == 2
    store.delete("memory_id = 'm1'")
    assert store.count() == 1


def test_staging_promote(store: SqliteVectorStore):
    store.upsert([_make_row("old", [1.0, 0.0, 0.0, 0.0])])
    assert store.count() == 1

    store.create_staging_table("memories_staging")
    store.upsert_into("memories_staging", [
        _make_row("new1", [0.0, 1.0, 0.0, 0.0]),
        _make_row("new2", [0.0, 0.0, 1.0, 0.0]),
    ])
    store.promote_staging("memories_staging")
    assert store.count() == 2
    results = store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert results[0]["memory_id"] == "new1"


def test_drop_and_recreate(store: SqliteVectorStore):
    store.upsert([_make_row("m1", [1.0, 0.0, 0.0, 0.0])])
    assert store.count() == 1
    store.drop_and_recreate()
    assert store.count() == 0


def test_select_columns(store: SqliteVectorStore):
    store.upsert([_make_row("m1", [1.0, 0.0, 0.0, 0.0])])
    results = store.search([1.0, 0.0, 0.0, 0.0], select_columns=["memory_id", "_distance"])
    assert len(results) == 1
    assert set(results[0].keys()) == {"memory_id", "_distance"}


def test_cosine_distance_correctness(store: SqliteVectorStore):
    store.upsert([_make_row("m1", [1.0, 0.0, 0.0, 0.0])])
    results = store.search([0.0, 1.0, 0.0, 0.0], top_k=1)
    assert abs(results[0]["_distance"] - 1.0) < 0.01

    results = store.search([-1.0, 0.0, 0.0, 0.0], top_k=1)
    assert abs(results[0]["_distance"] - 2.0) < 0.01
