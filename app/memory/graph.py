"""Memory graph: edges between cards for relationship tracking."""

from __future__ import annotations

import aiosqlite

from app.core.ids import generate_id


async def insert_edge(
    db_path: str,
    source_card_id: str,
    target_card_id: str,
    edge_type: str,
    weight: float = 1.0,
    confidence: float = 0.8,
) -> str:
    """Insert a directed edge between two cards."""
    edge_id = generate_id("edge_")
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO memory_edges
               (edge_id, source_card_id, target_card_id, edge_type, weight, confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (edge_id, source_card_id, target_card_id, edge_type, weight, confidence),
        )
        await db.commit()
    return edge_id


async def get_active_edges_for_cards(db_path: str, card_ids: list[str]) -> list[dict]:
    """Get all active edges touching any of the given cards."""
    if not card_ids:
        return []
    placeholders = ",".join(["?"] * len(card_ids))
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"""SELECT * FROM memory_edges
                WHERE status = 'active'
                AND (source_card_id IN ({placeholders}) OR target_card_id IN ({placeholders}))""",
            list(card_ids) + list(card_ids),
        )
        return [dict(r) for r in await cursor.fetchall()]
