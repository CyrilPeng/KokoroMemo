"""Retrieval gate decision methods for SQLiteStateStore."""

from __future__ import annotations

import json

import aiosqlite

from app.core.ids import generate_id


class RetrievalDecisionsMixin:
    async def list_retrieval_decisions(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM retrieval_decisions WHERE conversation_id = ?",
                (conversation_id,),
            )
            total = (await count_cursor.fetchone())[0]
            cursor = await db.execute(
                """SELECT * FROM retrieval_decisions WHERE conversation_id = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (conversation_id, limit, offset),
            )
            return [dict(row) for row in await cursor.fetchall()], total

    async def record_retrieval_decision(
        self,
        *,
        conversation_id: str,
        mode: str,
        should_retrieve: bool,
        reason: str,
        request_id: str | None = None,
        user_id: str | None = None,
        character_id: str | None = None,
        world_id: str | None = None,
        reasons: list[str] | None = None,
        skipped_routes: list[str] | None = None,
        triggered_routes: list[str] | None = None,
        latest_user_text: str | None = None,
        state_item_count: int = 0,
        avg_state_confidence: float | None = None,
        turn_index: int | None = None,
    ) -> str:
        await self.init_schema()
        decision_id = generate_id("gate_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO retrieval_decisions
                   (decision_id, request_id, conversation_id, user_id, character_id, world_id, mode,
                    should_retrieve, reason, reasons_json, skipped_routes_json, triggered_routes_json,
                    latest_user_text, state_confidence, state_item_count, avg_state_confidence, turn_index)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision_id, request_id, conversation_id, user_id, character_id, world_id, mode,
                    1 if should_retrieve else 0, reason,
                    json.dumps(reasons or [], ensure_ascii=False),
                    json.dumps(skipped_routes or [], ensure_ascii=False),
                    json.dumps(triggered_routes or reasons or [], ensure_ascii=False),
                    latest_user_text, avg_state_confidence, state_item_count, avg_state_confidence,
                    turn_index,
                ),
            )
            await db.commit()
        return decision_id

    async def list_retrieval_traces(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM retrieval_traces WHERE conversation_id = ?",
                (conversation_id,),
            )
            total = (await count_cursor.fetchone())[0]
            cursor = await db.execute(
                """SELECT * FROM retrieval_traces WHERE conversation_id = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (conversation_id, limit, offset),
            )
            return [dict(row) for row in await cursor.fetchall()], total

    async def get_retrieval_trace(self, trace_id: str) -> dict | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            trace_cursor = await db.execute(
                "SELECT * FROM retrieval_traces WHERE trace_id = ?",
                (trace_id,),
            )
            trace = await trace_cursor.fetchone()
            if not trace:
                return None
            candidates_cursor = await db.execute(
                """SELECT * FROM retrieval_trace_candidates WHERE trace_id = ?
                   ORDER BY selected DESC, final_score DESC, created_at ASC""",
                (trace_id,),
            )
            data = dict(trace)
            data["candidates"] = [dict(row) for row in await candidates_cursor.fetchall()]
            return data

    async def record_retrieval_trace(
        self,
        *,
        conversation_id: str,
        request_id: str | None = None,
        gate_decision_id: str | None = None,
        user_id: str | None = None,
        character_id: str | None = None,
        query_text: str | None = None,
        should_retrieve: bool = False,
        trigger_reason: str | None = None,
        retrieval_profile_id: str | None = None,
        retrieval_profile: dict | None = None,
        mounted_library_ids: list[str] | None = None,
        allowed_scopes: list[str] | None = None,
        candidates: list[dict] | None = None,
    ) -> str:
        await self.init_schema()
        trace_id = generate_id("trace_")
        candidate_rows = candidates or []
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO retrieval_traces
                   (trace_id, request_id, gate_decision_id, conversation_id, user_id, character_id,
                    query_text, should_retrieve, trigger_reason, retrieval_profile_id,
                    retrieval_profile_json, mounted_library_ids_json, allowed_scopes_json,
                    final_injected_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    request_id,
                    gate_decision_id,
                    conversation_id,
                    user_id,
                    character_id,
                    query_text,
                    1 if should_retrieve else 0,
                    trigger_reason,
                    retrieval_profile_id,
                    json.dumps(retrieval_profile or {}, ensure_ascii=False),
                    json.dumps(mounted_library_ids or [], ensure_ascii=False),
                    json.dumps(allowed_scopes or [], ensure_ascii=False),
                    sum(1 for item in candidate_rows if item.get("selected")),
                ),
            )
            for item in candidate_rows:
                await db.execute(
                    """INSERT INTO retrieval_trace_candidates
                       (candidate_id, trace_id, card_id, library_id, source_conversation_id,
                        source_character_id, route, vector_score, importance_score, recency_score,
                        scope_score, confidence_score, final_score, selected, filtered_reason,
                        injection_reason, content_preview)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        generate_id("rtc_"),
                        trace_id,
                        item.get("card_id"),
                        item.get("library_id"),
                        item.get("source_conversation_id"),
                        item.get("source_character_id"),
                        item.get("route"),
                        item.get("vector_score"),
                        item.get("importance_score"),
                        item.get("recency_score"),
                        item.get("scope_score"),
                        item.get("confidence_score"),
                        item.get("final_score"),
                        1 if item.get("selected") else 0,
                        item.get("filtered_reason"),
                        item.get("injection_reason"),
                        item.get("content_preview"),
                    ),
                )
            await db.commit()
        return trace_id

