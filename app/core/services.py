"""Global service instances (embedding provider, lancedb store)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.core.config import AppConfig
from app.providers.embedding_base import EmbeddingProvider
from app.providers.embedding_dummy import DummyEmbeddingProvider
from app.providers.embedding_openai_compatible import OpenAICompatibleEmbeddingProvider

try:
    from app.storage.lancedb_store import LanceDBStore
    _LANCEDB_AVAILABLE = True
except ImportError:
    _LANCEDB_AVAILABLE = False

logger = logging.getLogger("kokoromemo.services")


class ServiceRegistry:
    """Owns cached process services for the active app instance."""

    def __init__(self) -> None:
        self.embedding_provider: EmbeddingProvider | None = None
        self.embedding_signature: tuple | None = None
        self.lancedb_store: Any = None
        self.lancedb_signature: tuple | None = None
        self.index_migration_status: dict | None = None

    def reset(self) -> None:
        self.embedding_provider = None
        self.embedding_signature = None
        self.lancedb_store = None
        self.lancedb_signature = None

    def get_index_migration_status(self) -> dict | None:
        return self.index_migration_status

    def start_index_migration(self, cfg: AppConfig, old_model: str, old_dimension: int) -> None:
        from app.core.background import spawn_background

        self.index_migration_status = {
            "status": "running",
            "old_model": old_model,
            "old_dimension": old_dimension,
            "new_model": cfg.embedding.model,
            "new_dimension": cfg.embedding.dimension,
            "progress": 0,
            "total": 0,
            "error": None,
        }
        spawn_background(
            self._run_index_migration(cfg),
            name="index_migration",
        )

    async def _run_index_migration(self, cfg: AppConfig) -> None:
        try:
            from app.storage.rebuild_v2 import rebuild_vector_index_v2

            self.reset()
            ep = self.get_embedding_provider(cfg)
            store = self.get_lancedb_store(cfg)
            if not ep or not store:
                raise RuntimeError("Embedding provider or LanceDB store unavailable for migration")
            result = await rebuild_vector_index_v2(
                cards_db_path=cfg.storage.sqlite.memory_db,
                lancedb_store=store,
                embedding_provider=ep,
                batch_size=cfg.embedding.batch_size,
            )
            self.index_migration_status = {
                "status": "completed",
                "new_model": cfg.embedding.model,
                "new_dimension": cfg.embedding.dimension,
                "progress": result.get("rebuilt", 0),
                "total": result.get("total", 0),
                "error": None,
            }
            self.reset()
            logger.info("Index migration completed: %s", result)
        except Exception as exc:
            self.index_migration_status = {
                "status": "failed",
                "new_model": cfg.embedding.model,
                "new_dimension": cfg.embedding.dimension,
                "error": str(exc),
            }
            logger.error("Index migration failed: %s", exc)

    def get_embedding_provider(self, cfg: AppConfig) -> EmbeddingProvider | None:
        signature = (
            cfg.embedding.enabled,
            cfg.embedding.provider,
            cfg.embedding.base_url,
            cfg.embedding.get_api_key(),
            cfg.embedding.model,
            cfg.embedding.dimension,
            cfg.embedding.timeout_seconds,
        )
        if self.embedding_provider and self.embedding_signature == signature:
            return self.embedding_provider

        if not cfg.embedding.enabled:
            return None

        api_key = cfg.embedding.get_api_key()
        if not api_key:
            logger.warning("No embedding API key configured, using dummy provider")
            self.embedding_provider = DummyEmbeddingProvider(dimension=cfg.embedding.dimension or 4096)
            self.embedding_signature = signature
            return self.embedding_provider

        self.embedding_provider = OpenAICompatibleEmbeddingProvider(
            base_url=cfg.embedding.base_url,
            api_key=api_key,
            model=cfg.embedding.model,
            dimension=cfg.embedding.dimension,
            timeout=cfg.embedding.timeout_seconds,
        )
        self.embedding_signature = signature
        return self.embedding_provider

    def get_lancedb_store(self, cfg: AppConfig) -> Any:
        lancedb_path = resolve_lancedb_path(cfg)
        signature = (
            cfg.embedding.enabled,
            lancedb_path,
            cfg.storage.lancedb.table,
            cfg.embedding.dimension,
        )
        if self.lancedb_store and self.lancedb_signature == signature:
            return self.lancedb_store

        if not cfg.embedding.enabled:
            return None

        if _LANCEDB_AVAILABLE:
            self.lancedb_store = LanceDBStore(
                db_path=lancedb_path,
                table_name=cfg.storage.lancedb.table,
                dimension=cfg.embedding.dimension or 4096,
            )
        else:
            from app.storage.sqlite_vector_store import SqliteVectorStore
            sqlite_path = str(Path(lancedb_path) / "vectors.sqlite")
            self.lancedb_store = SqliteVectorStore(
                db_path=sqlite_path,
                table_name=cfg.storage.lancedb.table,
                dimension=cfg.embedding.dimension or 4096,
            )
            logger.info("LanceDB unavailable, using SQLite vector fallback: %s", sqlite_path)

        self.lancedb_store.connect()
        self.lancedb_signature = signature
        return self.lancedb_store


_service_registry = ServiceRegistry()


def set_service_registry(registry: ServiceRegistry) -> None:
    global _service_registry
    _service_registry = registry


def get_service_registry() -> ServiceRegistry:
    return _service_registry


def reset_services() -> None:
    """Clear cached service instances after config changes."""
    _service_registry.reset()


def get_index_migration_status() -> dict | None:
    """Return current index migration status if one is in progress."""
    return _service_registry.get_index_migration_status()


def start_index_migration(cfg: AppConfig, old_model: str, old_dimension: int) -> None:
    """Start a background index rebuild for a new embedding model."""
    _service_registry.start_index_migration(cfg, old_model, old_dimension)


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
    return _service_registry.get_embedding_provider(cfg)


def get_lancedb_store(cfg: AppConfig) -> Any:
    return _service_registry.get_lancedb_store(cfg)
