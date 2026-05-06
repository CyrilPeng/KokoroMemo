"""SQLite schema migration entrypoints."""

from app.storage.migrations.manager import apply_startup_migrations

__all__ = ["apply_startup_migrations"]
