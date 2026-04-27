"""Global app state holder to avoid circular imports."""

from __future__ import annotations

from app.core.config import AppConfig

_config: AppConfig | None = None


def get_config() -> AppConfig:
    assert _config is not None, "Config not initialized. Call set_config() first."
    return _config


def set_config(cfg: AppConfig) -> None:
    global _config
    _config = cfg
