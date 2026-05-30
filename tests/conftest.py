"""Shared test fixtures for KokoroMemo.

Provides reusable pytest fixtures that replace duplicated helpers previously
copy-pasted across individual test files:

- test_dir: temporary directory (auto-cleaned via pytest tmp_path)
- app_config: pre-configured AppConfig pointed at test_dir
- async_client: HTTPX AsyncClient wired to the test FastAPI app

Shared fake objects (FakeChatProvider, FakeLanceDBStore) are defined in
tests/_fakes.py and imported by test files directly.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import AppConfig
from app.core.state import set_config
from app.main import app


@pytest.fixture
def test_dir(tmp_path: Path) -> Path:
    """Provide a clean temporary directory, auto-cleaned by pytest."""
    return tmp_path


@pytest.fixture
def app_config(test_dir: Path) -> AppConfig:
    """Create and register a minimal AppConfig pointed at test_dir.

    Tests can mutate the returned config and call set_config(cfg) again
    if they change settings after initial setup.
    """
    cfg = AppConfig()
    cfg.storage.root_dir = str(test_dir)
    cfg.storage.sqlite.app_db = str(test_dir / "app.sqlite")
    cfg.storage.sqlite.memory_db = str(test_dir / "memory.sqlite")
    cfg.llm.base_url = "http://fake"
    cfg.llm.model = "fake-model"
    cfg.embedding.enabled = True
    cfg.memory.extraction_enabled = False
    cfg.memory.state_updater.enabled = False
    cfg.memory.retrieval_gate.vector_search_on_new_session = False
    set_config(cfg)
    return cfg


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTPX AsyncClient wired to the test FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
