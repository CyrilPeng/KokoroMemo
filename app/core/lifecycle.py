"""Application lifecycle service orchestration."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI

from app.core.background import BackgroundRunner, set_background_runner
from app.core.services import ServiceRegistry, set_service_registry
from app.proxy.llm_providers import close_llm_http_client
from app.storage.migrations import apply_startup_migrations
from app.storage.vector_sync import VectorSyncWorker

logger = logging.getLogger("kokoromemo")


class AppLifecycle:
    """Starts and stops process-wide runtime services in one place."""

    def __init__(self, app: FastAPI, cfg) -> None:
        self.app = app
        self.cfg = cfg
        self.registry = ServiceRegistry()
        self.background_runner = BackgroundRunner(max_concurrency=8)
        self.vector_sync_worker: VectorSyncWorker | None = None

    async def start(self) -> None:
        self._ensure_storage_dirs()
        await apply_startup_migrations(self.cfg)

        set_service_registry(self.registry)
        self.app.state.service_registry = self.registry

        set_background_runner(self.background_runner)
        self.app.state.background_runner = self.background_runner

        self.vector_sync_worker = VectorSyncWorker(self.cfg, service_registry=self.registry)
        self.vector_sync_worker.start()
        self.app.state.vector_sync_worker = self.vector_sync_worker

    async def stop(self) -> None:
        if self.vector_sync_worker is not None:
            await self.vector_sync_worker.stop()
        await self.background_runner.drain(timeout=30.0)
        await close_llm_http_client()
        set_background_runner(None)

    def _ensure_storage_dirs(self) -> None:
        root = Path(self.cfg.storage.root_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "conversations").mkdir(parents=True, exist_ok=True)
        (root / "memory").mkdir(parents=True, exist_ok=True)
        (root / "vector_indexes").mkdir(parents=True, exist_ok=True)
