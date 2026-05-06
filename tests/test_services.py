from app.core.config import AppConfig
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
