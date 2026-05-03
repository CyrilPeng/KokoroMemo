"""LanceDB vector store for memory retrieval."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

logger = logging.getLogger("kokoromemo.lancedb")


class LanceDBStore:
    def __init__(self, db_path: str, table_name: str = "memories", dimension: int = 4096):
        self.db_path = db_path
        self.table_name = table_name
        self.dimension = dimension
        self._db = None
        self._table = None

    def _get_schema(self) -> pa.Schema:
        return pa.schema([
            pa.field("memory_id", pa.string()),
            pa.field("library_id", pa.string()),
            pa.field("user_id", pa.string()),
            pa.field("character_id", pa.string()),
            pa.field("conversation_id", pa.string()),
            pa.field("scope", pa.string()),
            pa.field("memory_type", pa.string()),
            pa.field("content", pa.string()),
            pa.field("summary", pa.string()),
            pa.field("tags_json", pa.string()),
            pa.field("importance", pa.float32()),
            pa.field("confidence", pa.float32()),
            pa.field("status", pa.string()),
            pa.field("created_at", pa.string()),
            pa.field("updated_at", pa.string()),
            pa.field("embedding_model", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), self.dimension)),
        ])

    def connect(self) -> None:
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(self.db_path)
        try:
            self._table = self._db.open_table(self.table_name)
        except Exception:
            self._table = self._db.create_table(
                self.table_name, schema=self._get_schema()
            )
            logger.info("Created LanceDB table: %s", self.table_name)
            return
        self._validate_table_dimension()

    def _validate_table_dimension(self) -> None:
        """Ensure existing table vector dimension matches current embedding config."""
        if not self._table:
            return
        schema = self._table.schema
        vector_field = schema.field("vector")
        value_type = getattr(vector_field.type, "value_type", None)
        list_size = getattr(vector_field.type, "list_size", None)
        if value_type != pa.float32() or list_size != self.dimension:
            raise ValueError(
                f"LanceDB table dimension mismatch: expected {self.dimension}, got {list_size}"
            )

    def upsert(self, rows: list[dict[str, Any]]) -> None:
        """Insert or update memory vectors."""
        if not self._table:
            self.connect()
        # LanceDB 按 memory_id 执行 merge_insert
        self._table.merge_insert("memory_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)

    def search(
        self,
        query_vector: list[float],
        where: str | None = None,
        top_k: int = 30,
        select_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Vector search with optional metadata filter."""
        if not self._table:
            self.connect()

        q = self._table.search(query_vector, vector_column_name="vector")
        if where:
            q = q.where(where)
        if select_columns:
            q = q.select(select_columns)
        q = q.limit(top_k)
        results = q.to_list()
        return results

    def delete(self, where: str) -> None:
        """Delete rows matching filter."""
        if not self._table:
            self.connect()
        self._table.delete(where)

    def count(self) -> int:
        if not self._table:
            self.connect()
        return self._table.count_rows()

    def drop_and_recreate(self) -> None:
        """Drop table and recreate for full rebuild."""
        if not self._db:
            self.connect()
        try:
            self._db.drop_table(self.table_name)
        except Exception:
            pass
        self._table = self._db.create_table(self.table_name, schema=self._get_schema())

    def create_staging_table(self, staging_name: str) -> None:
        """Create (or recreate) a staging table parallel to the live one for atomic rebuild."""
        if not self._db:
            self.connect()
        try:
            self._db.drop_table(staging_name)
        except Exception:
            pass
        self._db.create_table(staging_name, schema=self._get_schema())

    def upsert_into(self, staging_name: str, rows: list[dict[str, Any]]) -> None:
        """Upsert rows into a named staging table (used during atomic rebuild)."""
        if not self._db:
            self.connect()
        staging = self._db.open_table(staging_name)
        staging.merge_insert("memory_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)

    def promote_staging(self, staging_name: str) -> None:
        """Atomically replace the live table with the staging table.

        After all writes have completed successfully into staging, drop the live table and
        rename staging to the live name. If anything has failed before this is called, the
        live table is untouched.
        """
        if not self._db:
            self.connect()
        try:
            self._db.drop_table(self.table_name)
        except Exception:
            pass
        self._db.rename_table(staging_name, self.table_name)
        self._table = self._db.open_table(self.table_name)

    def drop_staging(self, staging_name: str) -> None:
        """Drop a staging table. Used to clean up after a failed rebuild."""
        if not self._db:
            self.connect()
        try:
            self._db.drop_table(staging_name)
        except Exception:
            pass
