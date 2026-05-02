"""SQLite + numpy vector store — fallback when LanceDB is unavailable (e.g. ARM/Termux)."""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("kokoromemo.sqlite_vector")

_META_COLUMNS = [
    "memory_id", "library_id", "user_id", "character_id", "conversation_id",
    "scope", "memory_type", "content", "summary", "tags_json",
    "importance", "confidence", "status", "created_at", "updated_at",
    "embedding_model",
]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    memory_id     TEXT PRIMARY KEY,
    library_id    TEXT,
    user_id       TEXT,
    character_id  TEXT,
    conversation_id TEXT,
    scope         TEXT,
    memory_type   TEXT,
    content       TEXT,
    summary       TEXT,
    tags_json     TEXT,
    importance    REAL,
    confidence    REAL,
    status        TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    embedding_model TEXT,
    vector        BLOB
)
"""


class SqliteVectorStore:
    def __init__(self, db_path: str, table_name: str = "memories", dimension: int = 4096):
        self.db_path = db_path
        self.table_name = table_name
        self.dimension = dimension
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_CREATE_TABLE_SQL.format(table=self.table_name))
        self._conn.commit()
        logger.info("SQLite vector store connected: %s (table=%s, dim=%d)", self.db_path, self.table_name, self.dimension)

    def _ensure_conn(self) -> sqlite3.Connection:
        if not self._conn:
            self.connect()
        return self._conn  # type: ignore[return-value]

    @staticmethod
    def _vector_to_blob(vec: list[float] | np.ndarray) -> bytes:
        return np.asarray(vec, dtype=np.float32).tobytes()

    @staticmethod
    def _blob_to_vector(blob: bytes) -> np.ndarray:
        return np.frombuffer(blob, dtype=np.float32)

    def upsert(self, rows: list[dict[str, Any]]) -> None:
        conn = self._ensure_conn()
        cols = _META_COLUMNS + ["vector"]
        placeholders = ", ".join(["?"] * len(cols))
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "memory_id")
        sql = (
            f"INSERT INTO {self.table_name} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(memory_id) DO UPDATE SET {updates}"
        )
        for row in rows:
            values = [row.get(c) for c in _META_COLUMNS]
            values.append(self._vector_to_blob(row["vector"]))
            conn.execute(sql, values)
        conn.commit()

    def search(
        self,
        query_vector: list[float],
        where: str | None = None,
        top_k: int = 30,
        select_columns: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        conn = self._ensure_conn()

        filter_clause = ""
        params: list[Any] = []
        if where:
            filter_clause, params = self._parse_where(where)
            filter_clause = f" WHERE {filter_clause}"

        cur = conn.execute(
            f"SELECT {', '.join(_META_COLUMNS)}, vector FROM {self.table_name}{filter_clause}",
            params,
        )
        rows_raw = cur.fetchall()
        if not rows_raw:
            return []

        q = np.asarray(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            q_norm = 1.0

        results: list[tuple[float, dict[str, Any]]] = []
        for row in rows_raw:
            meta = dict(zip(_META_COLUMNS, row[:-1]))
            vec = self._blob_to_vector(row[-1])
            v_norm = np.linalg.norm(vec)
            if v_norm == 0:
                dist = 1.0
            else:
                dist = 1.0 - float(np.dot(q, vec) / (q_norm * v_norm))
            meta["_distance"] = dist
            results.append((dist, meta))

        results.sort(key=lambda x: x[0])
        output = [r[1] for r in results[:top_k]]
        if select_columns:
            output = [{k: r[k] for k in select_columns if k in r} for r in output]
        return output

    def delete(self, where: str) -> None:
        conn = self._ensure_conn()
        filter_clause, params = self._parse_where(where)
        conn.execute(f"DELETE FROM {self.table_name} WHERE {filter_clause}", params)
        conn.commit()

    def count(self) -> int:
        conn = self._ensure_conn()
        cur = conn.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        return cur.fetchone()[0]

    def drop_and_recreate(self) -> None:
        conn = self._ensure_conn()
        conn.execute(f"DROP TABLE IF EXISTS {self.table_name}")
        conn.execute(_CREATE_TABLE_SQL.format(table=self.table_name))
        conn.commit()

    def create_staging_table(self, staging_name: str) -> None:
        conn = self._ensure_conn()
        conn.execute(f"DROP TABLE IF EXISTS {staging_name}")
        conn.execute(_CREATE_TABLE_SQL.format(table=staging_name))
        conn.commit()

    def upsert_into(self, staging_name: str, rows: list[dict[str, Any]]) -> None:
        conn = self._ensure_conn()
        cols = _META_COLUMNS + ["vector"]
        placeholders = ", ".join(["?"] * len(cols))
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "memory_id")
        sql = (
            f"INSERT INTO {staging_name} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(memory_id) DO UPDATE SET {updates}"
        )
        for row in rows:
            values = [row.get(c) for c in _META_COLUMNS]
            values.append(self._vector_to_blob(row["vector"]))
            conn.execute(sql, values)
        conn.commit()

    def promote_staging(self, staging_name: str) -> None:
        conn = self._ensure_conn()
        conn.execute(f"DROP TABLE IF EXISTS {self.table_name}")
        conn.execute(f"ALTER TABLE {staging_name} RENAME TO {self.table_name}")
        conn.commit()

    def drop_staging(self, staging_name: str) -> None:
        conn = self._ensure_conn()
        try:
            conn.execute(f"DROP TABLE IF EXISTS {staging_name}")
            conn.commit()
        except Exception:
            pass

    @staticmethod
    def _parse_where(where: str) -> tuple[str, list[Any]]:
        """Convert a LanceDB-style filter string to parameterized SQL.

        The filters produced by card_retriever.py are already valid SQL syntax,
        so we just need to extract string literals into bind parameters.
        """
        params: list[Any] = []
        pattern = re.compile(r"'((?:[^']|'')*)'")

        def replacer(m: re.Match) -> str:
            params.append(m.group(1).replace("''", "'"))
            return "?"

        sql = pattern.sub(replacer, where)
        return sql, params
