"""Memory summaries: L3 session stage and L4 user/character profiles.

Currently a placeholder — summary generation will be triggered manually or via
a background job in future versions.
"""

from __future__ import annotations

import aiosqlite

from app.core.ids import generate_id


async def insert_summary(
    db_path: str,
    level: int,
    summary_type: str,
    content: str,
    user_id: str,
    character_id: str | None = None,
    conversation_id: str | None = None,
    title: str | None = None,
    importance: float = 0.6,
    confidence: float = 0.7,
    source_card_ids_json: str | None = None,
) -> str:
    """Insert a memory summary."""
    summary_id = generate_id("sum_")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO memory_summaries
               (summary_id, level, summary_type, title, content, user_id,
                character_id, conversation_id, importance, confidence, source_card_ids_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (summary_id, level, summary_type, title, content, user_id,
             character_id, conversation_id, importance, confidence, source_card_ids_json),
        )
        await db.commit()
    return summary_id


async def get_active_summaries(
    db_path: str, user_id: str, character_id: str | None = None, level: int | None = None
) -> list[dict]:
    """Get active summaries, optionally filtered by level."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM memory_summaries WHERE status = 'active' AND user_id = ?"
        params: list = [user_id]
        if character_id:
            query += " AND (character_id = ? OR character_id IS NULL)"
            params.append(character_id)
        if level is not None:
            query += " AND level = ?"
            params.append(level)
        query += " ORDER BY level DESC, importance DESC"
        cursor = await db.execute(query, params)
        return [dict(r) for r in await cursor.fetchall()]
