import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

from app.storage.migrations.manager import (
    DatabaseMigrationTarget,
    Migration,
    apply_migrations,
    apply_startup_migrations,
    get_schema_version,
)


_WORK_ROOT = Path(".test_migrations_work")


def _work_dir(name: str) -> Path:
    base = _WORK_ROOT / name
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _cleanup_work_dir() -> None:
    shutil.rmtree(_WORK_ROOT, ignore_errors=True)


def test_apply_migrations_records_version():
    async def run():
        calls = []
        db_path = str(_work_dir("custom") / "custom.sqlite")

        async def migration_one(path: str) -> None:
            calls.append((1, path))

        async def migration_two(path: str) -> None:
            calls.append((2, path))

        target = DatabaseMigrationTarget(
            "custom",
            db_path,
            (
                Migration(1, "one", migration_one),
                Migration(2, "two", migration_two),
            ),
        )
        await apply_migrations(target)
        await apply_migrations(target)

        assert calls == [(1, db_path), (2, db_path)]
        assert await get_schema_version(db_path, "custom") == 2

    try:
        asyncio.run(run())
    finally:
        _cleanup_work_dir()


def test_startup_migrations_create_app_and_memory_schema():
    async def run():
        base = _work_dir("startup")
        cfg = SimpleNamespace(
            storage=SimpleNamespace(
                sqlite=SimpleNamespace(
                    app_db=str(base / "app.sqlite"),
                    memory_db=str(base / "memory.sqlite"),
                )
            )
        )

        await apply_startup_migrations(cfg)

        assert await get_schema_version(cfg.storage.sqlite.app_db, "app") == 1
        assert await get_schema_version(cfg.storage.sqlite.memory_db, "memory") == 1

    try:
        asyncio.run(run())
    finally:
        _cleanup_work_dir()
