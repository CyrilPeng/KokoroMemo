"""Backend-neutral contract for vector stores."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    backend_name: str
    table_name: str
    dimension: int

    def connect(self) -> None: ...

    def upsert(self, rows: list[dict[str, Any]]) -> None: ...

    def search(
        self,
        query_vector: list[float],
        where: str | None = None,
        top_k: int = 30,
        select_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def delete(self, where: str) -> None: ...

    def count(self) -> int: ...

    def drop_and_recreate(self) -> None: ...

    def create_staging_table(self, staging_name: str) -> None: ...

    def upsert_into(self, staging_name: str, rows: list[dict[str, Any]]) -> None: ...

    def promote_staging(self, staging_name: str) -> None: ...

    def drop_staging(self, staging_name: str) -> None: ...
