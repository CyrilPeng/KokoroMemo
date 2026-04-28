"""Project approved long-term cards into conversation hot-state."""

from __future__ import annotations

import aiosqlite

from app.memory.state_schema import ConversationStateItem
from app.storage.sqlite_state import SQLiteStateStore


async def project_cards_to_state(
    db_path: str,
    conversation_id: str,
    user_id: str | None = None,
    character_id: str | None = None,
) -> dict:
    """Project approved boundary/preference cards into active state items."""
    store = SQLiteStateStore(db_path)
    await store.init_schema()
    where = ["status = 'approved'", "card_type IN ('boundary', 'preference')"]
    params: list = []
    if user_id:
        where.append("user_id = ?")
        params.append(user_id)
    if character_id:
        where.append("(character_id = ? OR character_id IS NULL)")
        params.append(character_id)
    where.append("(conversation_id = ? OR conversation_id IS NULL)")
    params.append(conversation_id)
    where_sql = " AND ".join(where)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""SELECT * FROM memory_cards WHERE {where_sql}
                ORDER BY is_pinned DESC, importance DESC, updated_at DESC LIMIT 100""",
            params,
        )
        rows = await cursor.fetchall()

    projected = 0
    for row in rows:
        category = row["card_type"]
        await store.upsert_item(ConversationStateItem(
            item_id=None,
            user_id=row["user_id"],
            character_id=row["character_id"],
            conversation_id=conversation_id,
            category=category,
            item_key=f"card_{row['card_id']}",
            title="长期边界" if category == "boundary" else "长期偏好",
            content=row["content"],
            confidence=row["confidence"],
            priority=100 if row["is_pinned"] else 75,
            source="card_projection",
            linked_card_ids=[row["card_id"]],
            metadata={"projected_from_card": row["card_id"]},
        ))
        projected += 1
    await store.record_state_event(
        conversation_id,
        "project_cards",
        payload={"projected": projected, "user_id": user_id, "character_id": character_id},
    )
    return {"projected": projected}
