import asyncio
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

from app.core.background import get_background_runner
from app.core.config import AppConfig
from app.core.lifecycle import AppLifecycle


class DummyApp:
    def __init__(self):
        self.state = SimpleNamespace()


def _make_work_dir() -> Path:
    root = Path(".test_lifecycle") / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_app_lifecycle_starts_and_stops_runtime_services():
    async def run():
        root = _make_work_dir()
        try:
            cfg = AppConfig()
            cfg.storage.root_dir = str(root)
            cfg.storage.sqlite.app_db = str(root / "app.sqlite")
            cfg.storage.sqlite.memory_db = str(root / "memory.sqlite")
            cfg.embedding.enabled = False
            app = DummyApp()
            lifecycle = AppLifecycle(app, cfg)

            await lifecycle.start()

            assert (root / "conversations").is_dir()
            assert (root / "memory").is_dir()
            assert (root / "vector_indexes").is_dir()
            assert app.state.service_registry is lifecycle.registry
            assert app.state.background_runner is lifecycle.background_runner
            assert app.state.vector_sync_worker is lifecycle.vector_sync_worker
            assert get_background_runner() is lifecycle.background_runner

            await lifecycle.stop()
            assert get_background_runner() is None
        finally:
            shutil.rmtree(root, ignore_errors=True)

    asyncio.run(run())
