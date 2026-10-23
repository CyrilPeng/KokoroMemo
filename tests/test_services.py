import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import AppConfig, load_config
from app.core.services import (
    ServiceRegistry,
    get_embedding_provider,
    normalize_vector_store,
    reset_services,
    set_service_registry,
)
from app.providers.embedding_dummy import DummyEmbeddingProvider
from app.storage.sqlite_vector_store import SqliteVectorStore
from app.storage.vector_store_base import VectorStore


def test_service_registry_isolates_cached_embedding_provider():
    cfg = AppConfig()
    cfg.embedding.enabled = True
    cfg.embedding.api_key = ""
    cfg.embedding.dimension = 8

    first_registry = ServiceRegistry()
    set_service_registry(first_registry)
    first_provider = get_embedding_provider(cfg)
    assert isinstance(first_provider, DummyEmbeddingProvider)
    assert get_embedding_provider(cfg) is first_provider

    second_registry = ServiceRegistry()
    set_service_registry(second_registry)
    second_provider = get_embedding_provider(cfg)
    assert isinstance(second_provider, DummyEmbeddingProvider)
    assert second_provider is not first_provider

    reset_services()


def test_extraction_semantic_dedup_threshold_loads_from_config():
    test_dir = Path(".test_tmp") / uuid4().hex
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        config_path = test_dir / "config.yaml"
        config_path.write_text(
            "memory:\n  extraction:\n    semantic_dedup_threshold: 0.87\n",
            encoding="utf-8",
        )

        cfg = load_config(config_path)

        assert cfg.memory.extraction.semantic_dedup_threshold == 0.87
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_vector_store_mode_loads_from_config():
    test_dir = Path(".test_tmp") / uuid4().hex
    test_dir.mkdir(parents=True, exist_ok=True)
    try:
        config_path = test_dir / "config.yaml"
        config_path.write_text("storage:\n  vector_store: sqlite\n", encoding="utf-8")

        cfg = load_config(config_path)

        assert cfg.storage.vector_store == "sqlite"
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


def test_unknown_vector_store_mode_falls_back_to_auto():
    assert normalize_vector_store("unknown") == "auto"
    assert normalize_vector_store(None) == "auto"


def test_sqlite_vector_store_mode_uses_sqlite(tmp_path):
    cfg = AppConfig()
    cfg.storage.root_dir = str(tmp_path)
    cfg.storage.vector_store = "sqlite"
    cfg.embedding.dimension = 8

    store = ServiceRegistry().get_vector_store(cfg)

    assert isinstance(store, SqliteVectorStore)
    assert isinstance(store, VectorStore)


def test_vector_store_getter_keeps_deprecated_alias(tmp_path):
    cfg = AppConfig()
    cfg.storage.root_dir = str(tmp_path)
    cfg.storage.vector_store = "sqlite"
    cfg.embedding.dimension = 8
    registry = ServiceRegistry()

    store = registry.get_vector_store(cfg)
    assert registry.get_lancedb_store(cfg) is store


def test_lancedb_mode_raises_when_backend_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.services._LANCEDB_AVAILABLE", False)
    monkeypatch.setattr("app.core.services._LANCEDB_IMPORT_ERROR", ImportError("no AVX2"))
    cfg = AppConfig()
    cfg.storage.root_dir = str(tmp_path)
    cfg.storage.vector_store = "lancedb"
    cfg.embedding.dimension = 8

    with pytest.raises(RuntimeError, match="LanceDB is not available"):
        ServiceRegistry().get_lancedb_store(cfg)


def test_auto_mode_falls_back_to_sqlite_when_lancedb_init_fails(tmp_path, monkeypatch):
    class BrokenLanceDBStore:
        def __init__(self, **kwargs):
            pass

        def connect(self):
            raise RuntimeError("illegal instruction")

    monkeypatch.setattr("app.core.services._LANCEDB_AVAILABLE", True)
    monkeypatch.setattr("app.core.services.LanceDBStore", BrokenLanceDBStore, raising=False)
    cfg = AppConfig()
    cfg.storage.root_dir = str(tmp_path)
    cfg.storage.vector_store = "auto"
    cfg.embedding.dimension = 8

    store = ServiceRegistry().get_lancedb_store(cfg)

    assert isinstance(store, SqliteVectorStore)
