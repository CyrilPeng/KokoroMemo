"""SQLite storage for app-level data (conversations registry, users, characters)."""

from __future__ import annotations

import json

import aiosqlite
from pathlib import Path

from app.memory.conversation_policy import get_profile

_APP_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  display_name TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS characters (
  character_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  display_name TEXT,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  notes TEXT,
  source TEXT,
  system_prompt_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS character_defaults (
  character_id TEXT PRIMARY KEY,
  profile_id TEXT,
  template_id TEXT,
  table_template_id TEXT,
  mount_preset_id TEXT,
  memory_write_policy TEXT,
  state_update_policy TEXT,
  injection_policy TEXT,
  library_ids_json TEXT NOT NULL DEFAULT '["lib_default"]',
  write_library_id TEXT,
  auto_apply INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  character_id TEXT,
  client_name TEXT,
  title TEXT,
  path TEXT NOT NULL,
  first_seen_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  status TEXT NOT NULL DEFAULT 'active'
);
"""


_CHARACTER_COLUMNS = {
    "aliases_json": "TEXT NOT NULL DEFAULT '[]'",
    "notes": "TEXT",
    "source": "TEXT",
}


_CHARACTER_DEFAULT_COLUMNS = {
    "profile_id": "TEXT",
    "table_template_id": "TEXT",
    "mount_preset_id": "TEXT",
    "memory_write_policy": "TEXT",
    "state_update_policy": "TEXT",
    "injection_policy": "TEXT",
}


async def _ensure_columns(db: aiosqlite.Connection, table: str, columns: dict[str, str]) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


async def init_app_db(db_path: str) -> None:
    """Initialize app.sqlite with schema."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_APP_SCHEMA)
        await _ensure_columns(db, "characters", _CHARACTER_COLUMNS)
        await _ensure_columns(db, "character_defaults", _CHARACTER_DEFAULT_COLUMNS)
        await db.commit()


async def upsert_conversation(
    db_path: str,
    conversation_id: str,
    user_id: str,
    character_id: str | None,
    client_name: str | None,
    conv_path: str,
) -> None:
    """Register or update a conversation in app.sqlite."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO conversations (conversation_id, user_id, character_id, client_name, path, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'))
            ON CONFLICT(conversation_id) DO UPDATE SET
              last_seen_at = datetime('now', 'localtime'),
              character_id = COALESCE(excluded.character_id, conversations.character_id),
              client_name = COALESCE(excluded.client_name, conversations.client_name)
            """,
            (conversation_id, user_id, character_id, client_name, conv_path),
        )
        await db.commit()


async def upsert_character(
    db_path: str,
    character_id: str,
    user_id: str,
    display_name: str | None = None,
    system_prompt_hash: str | None = None,
    source: str | None = None,
) -> None:
    """Register or refresh a character row when first seen.

    The characters table is the canonical record of "which characters this user has interacted with";
    insertion happens lazily when a chat request with a known character_id arrives.
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO characters (character_id, user_id, display_name, system_prompt_hash, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(character_id) DO UPDATE SET
              updated_at = datetime('now', 'localtime'),
              display_name = COALESCE(excluded.display_name, characters.display_name),
              system_prompt_hash = COALESCE(excluded.system_prompt_hash, characters.system_prompt_hash),
              source = COALESCE(excluded.source, characters.source)
            """,
            (character_id, user_id, display_name, system_prompt_hash, source),
        )
        await db.commit()


async def update_character_profile(
    db_path: str,
    character_id: str,
    display_name: str | None = None,
    aliases: list[str] | None = None,
    notes: str | None = None,
    source: str | None = None,
    user_id: str = "default",
) -> None:
    aliases_json = json.dumps(aliases or [], ensure_ascii=False)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO characters (character_id, user_id, display_name, aliases_json, notes, source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(character_id) DO UPDATE SET
              display_name = excluded.display_name,
              aliases_json = excluded.aliases_json,
              notes = excluded.notes,
              source = excluded.source,
              updated_at = datetime('now', 'localtime')
            """,
            (character_id, user_id, display_name, aliases_json, notes, source),
        )
        await db.commit()


async def get_character_defaults(db_path: str, character_id: str) -> dict | None:
    """Get default template and library config for a character."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM character_defaults WHERE character_id = ?",
            (character_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "character_id": row["character_id"],
            "profile_id": row["profile_id"],
            "template_id": row["template_id"],
            "table_template_id": row["table_template_id"],
            "mount_preset_id": row["mount_preset_id"],
            "memory_write_policy": row["memory_write_policy"],
            "state_update_policy": row["state_update_policy"],
            "injection_policy": row["injection_policy"],
            "library_ids": json.loads(row["library_ids_json"]),
            "write_library_id": row["write_library_id"],
            "auto_apply": bool(row["auto_apply"]),
        }


async def set_character_defaults(
    db_path: str,
    character_id: str,
    profile_id: str | None = None,
    template_id: str | None = None,
    table_template_id: str | None = None,
    mount_preset_id: str | None = None,
    memory_write_policy: str | None = None,
    state_update_policy: str | None = None,
    injection_policy: str | None = None,
    library_ids: list[str] | None = None,
    write_library_id: str | None = None,
    auto_apply: bool = True,
) -> None:
    """Save default template and library config for a character."""
    profile = get_profile(profile_id)
    profile_id = profile_id or profile.profile_id
    template_id = template_id if template_id is not None else profile.template_id
    table_template_id = table_template_id if table_template_id is not None else profile.table_template_id
    mount_preset_id = mount_preset_id if mount_preset_id is not None else profile.mount_preset_id
    memory_write_policy = memory_write_policy or profile.memory_write_policy
    state_update_policy = state_update_policy or profile.state_update_policy
    injection_policy = injection_policy or profile.injection_policy
    library_ids_json = json.dumps(library_ids or ["lib_default"])
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO character_defaults
              (character_id, profile_id, template_id, table_template_id, mount_preset_id,
               memory_write_policy, state_update_policy, injection_policy,
               library_ids_json, write_library_id, auto_apply)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(character_id) DO UPDATE SET
              profile_id = excluded.profile_id,
              template_id = excluded.template_id,
              table_template_id = excluded.table_template_id,
              mount_preset_id = excluded.mount_preset_id,
              memory_write_policy = excluded.memory_write_policy,
              state_update_policy = excluded.state_update_policy,
              injection_policy = excluded.injection_policy,
              library_ids_json = excluded.library_ids_json,
              write_library_id = excluded.write_library_id,
              auto_apply = excluded.auto_apply,
              updated_at = datetime('now', 'localtime')
            """,
            (
                character_id,
                profile_id,
                template_id,
                table_template_id,
                mount_preset_id,
                memory_write_policy,
                state_update_policy,
                injection_policy,
                library_ids_json,
                write_library_id,
                int(auto_apply),
            ),
        )
        await db.commit()


async def list_characters(db_path: str) -> list[dict]:
    """List all known characters."""
    await init_app_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
              c.*,
              cd.profile_id, cd.template_id, cd.table_template_id, cd.mount_preset_id,
              cd.memory_write_policy, cd.state_update_policy, cd.injection_policy,
              cd.library_ids_json, cd.write_library_id, cd.auto_apply,
              COUNT(conv.conversation_id) AS conversation_count,
              MIN(conv.first_seen_at) AS first_seen_at,
              MAX(conv.last_seen_at) AS last_seen_at
            FROM characters c
            LEFT JOIN character_defaults cd ON c.character_id = cd.character_id
            LEFT JOIN conversations conv ON c.character_id = conv.character_id
            GROUP BY c.character_id
            ORDER BY COALESCE(MAX(conv.last_seen_at), c.updated_at) DESC
            """
        )
        rows = await cursor.fetchall()
        return [
            {
                "character_id": row["character_id"],
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "aliases": json.loads(row["aliases_json"] or "[]"),
                "notes": row["notes"],
                "source": row["source"],
                "system_prompt_hash": row["system_prompt_hash"],
                "profile_id": row["profile_id"],
                "template_id": row["template_id"],
                "table_template_id": row["table_template_id"],
                "mount_preset_id": row["mount_preset_id"],
                "memory_write_policy": row["memory_write_policy"],
                "state_update_policy": row["state_update_policy"],
                "injection_policy": row["injection_policy"],
                "library_ids": json.loads(row["library_ids_json"]) if row["library_ids_json"] else None,
                "write_library_id": row["write_library_id"],
                "auto_apply": bool(row["auto_apply"]) if row["auto_apply"] is not None else None,
                "conversation_count": row["conversation_count"] or 0,
                "first_seen_at": row["first_seen_at"] or row["created_at"],
                "last_seen_at": row["last_seen_at"] or row["updated_at"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]


async def discover_characters(db_path: str) -> list[dict]:
    """Discover characters from conversations and merge with defaults.

    The `characters` table is currently never populated by code; characters are
    only known implicitly through the `character_id` column on conversations.
    This helper derives a per-character summary from conversations and merges
    in the configured defaults from `character_defaults`.
    """
    await init_app_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT
              c.character_id AS character_id,
              ch.display_name AS display_name,
              ch.aliases_json AS aliases_json,
              ch.notes AS notes,
              ch.source AS source,
              MAX(c.last_seen_at) AS last_seen_at,
              MIN(c.first_seen_at) AS first_seen_at,
              COUNT(*) AS conversation_count,
              cd.profile_id AS profile_id,
              cd.template_id AS template_id,
              cd.table_template_id AS table_template_id,
              cd.mount_preset_id AS mount_preset_id,
              cd.memory_write_policy AS memory_write_policy,
              cd.state_update_policy AS state_update_policy,
              cd.injection_policy AS injection_policy,
              cd.library_ids_json AS library_ids_json,
              cd.write_library_id AS write_library_id,
              cd.auto_apply AS auto_apply
            FROM conversations c
            LEFT JOIN characters ch ON c.character_id = ch.character_id
            LEFT JOIN character_defaults cd ON c.character_id = cd.character_id
            WHERE c.character_id IS NOT NULL AND c.character_id != ''
            GROUP BY c.character_id
            ORDER BY MAX(c.last_seen_at) DESC
            """
        )
        rows = await cursor.fetchall()
        return [
            {
                "character_id": row["character_id"],
                "display_name": row["display_name"],
                "aliases": json.loads(row["aliases_json"] or "[]"),
                "notes": row["notes"],
                "source": row["source"],
                "conversation_count": row["conversation_count"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "profile_id": row["profile_id"],
                "template_id": row["template_id"],
                "table_template_id": row["table_template_id"],
                "mount_preset_id": row["mount_preset_id"],
                "memory_write_policy": row["memory_write_policy"],
                "state_update_policy": row["state_update_policy"],
                "injection_policy": row["injection_policy"],
                "library_ids": json.loads(row["library_ids_json"]) if row["library_ids_json"] else None,
                "write_library_id": row["write_library_id"],
                "auto_apply": bool(row["auto_apply"]) if row["auto_apply"] is not None else None,
            }
            for row in rows
        ]


async def list_conversations(db_path: str, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """List recent conversations ordered by last_seen_at descending."""
    await init_app_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT COUNT(*) FROM conversations")
        total = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT conversation_id, user_id, character_id, client_name, last_seen_at, first_seen_at "
            "FROM conversations ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        items = [
            {
                "conversation_id": row["conversation_id"],
                "user_id": row["user_id"],
                "character_id": row["character_id"],
                "client_name": row["client_name"],
                "last_seen_at": row["last_seen_at"],
                "first_seen_at": row["first_seen_at"],
            }
            for row in rows
        ]
        return items, total


async def list_character_conversations(db_path: str, character_id: str) -> list[dict]:
    await init_app_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT conversation_id, user_id, character_id, client_name, first_seen_at, last_seen_at
               FROM conversations
               WHERE character_id = ?
               ORDER BY last_seen_at DESC""",
            (character_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def delete_conversation(db_path: str, conversation_id: str) -> bool:
    """Delete a conversation record from app.sqlite."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        await db.commit()
        return cursor.rowcount > 0
