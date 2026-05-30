import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import AppConfig, load_config
from app.core.services import ServiceRegistry, get_embedding_provider, reset_services, set_service_registry
from app.providers.embedding_dummy import DummyEmbeddingProvider


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
