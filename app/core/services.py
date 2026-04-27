"""Global service instances (embedding provider, lancedb store)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.config import AppConfig
from app.providers.embedding_base import EmbeddingProvider
from app.providers.embedding_dummy import DummyEmbeddingProvider
from app.providers.embedding_openai_compatible import OpenAICompatibleEmbeddingProvider
from app.storage.lancedb_store import LanceDBStore

logger = logging.getLogger("kokoromemo.services")

_embedding_provider: EmbeddingProvider | None = None
_embedding_signature: tuple | None = None
_lancedb_store: LanceDBStore | None = None
_lancedb_signature: tuple | None = None


def reset_services() -> None:
    """Clear cached service instances after config changes."""
    global _embedding_provider, _embedding_signature, _lancedb_store, _lancedb_signature
    _embedding_provider = None
    _embedding_signature = None
    _lancedb_store = None
    _lancedb_signature = None


def _safe_index_name(model: str, dimension: int) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", model).strip("_").lower()
    return f"{normalized or 'embedding'}_{dimension}"


def resolve_lancedb_path(cfg: AppConfig) -> str:
    """Resolve model/dimension-specific LanceDB path."""
    configured = Path(cfg.storage.lancedb.path)
    expected_name = _safe_index_name(cfg.embedding.model, cfg.embedding.dimension)
    if configured.name == "lancedb":
        parent = configured.parent
        if parent.name.endswith(f"_{cfg.embedding.dimension}") and cfg.embedding.model.replace("-", "_") in parent.name:
            return str(configured)
    return str(Path(cfg.storage.root_dir, "vector_indexes", expected_name, "lancedb"))


def get_embedding_provider(cfg: AppConfig) -> EmbeddingProvider | None:
    global _embedding_provider, _embedding_signature
    signature = (
        cfg.embedding.enabled,
        cfg.embedding.provider,
        cfg.embedding.base_url,
        cfg.embedding.get_api_key(),
        cfg.embedding.model,
        cfg.embedding.dimension,
        cfg.embedding.timeout_seconds,
    )
    if _embedding_provider and _embedding_signature == signature:
        return _embedding_provider

    if not cfg.embedding.enabled:
        return None

    api_key = cfg.embedding.get_api_key()
    if not api_key:
        logger.warning("No embedding API key configured, using dummy provider")
        _embedding_provider = DummyEmbeddingProvider(dimension=cfg.embedding.dimension or 4096)
        _embedding_signature = signature
        return _embedding_provider

    _embedding_provider = OpenAICompatibleEmbeddingProvider(
        base_url=cfg.embedding.base_url,
        api_key=api_key,
        model=cfg.embedding.model,
        dimension=cfg.embedding.dimension,
        timeout=cfg.embedding.timeout_seconds,
    )
    _embedding_signature = signature
    return _embedding_provider


def get_lancedb_store(cfg: AppConfig) -> LanceDBStore | None:
    global _lancedb_store, _lancedb_signature
    lancedb_path = resolve_lancedb_path(cfg)
    signature = (
        cfg.embedding.enabled,
        lancedb_path,
        cfg.storage.lancedb.table,
        cfg.embedding.dimension,
    )
    if _lancedb_store and _lancedb_signature == signature:
        return _lancedb_store

    if not cfg.embedding.enabled:
        return None

    _lancedb_store = LanceDBStore(
        db_path=lancedb_path,
        table_name=cfg.storage.lancedb.table,
        dimension=cfg.embedding.dimension or 4096,
    )
    _lancedb_store.connect()
    _lancedb_signature = signature
    return _lancedb_store
