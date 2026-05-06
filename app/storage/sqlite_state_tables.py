"""State table template, row and event methods for SQLiteStateStore."""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from app.core.ids import generate_id
from app.memory.state_schema import (
    StateTableCell,
    StateTableColumn,
    StateTableRow,
    StateTableSchema,
    StateTableTemplate,
)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _row_to_table_column(row: aiosqlite.Row) -> StateTableColumn:
    return StateTableColumn(
        column_id=row["column_id"],
        table_id=row["table_id"],
        column_key=row["column_key"],
        name=row["name"],
        description=row["description"] or "",
        value_type=row["value_type"],
        required=bool(row["required"]),
        sort_order=int(row["sort_order"]),
        include_in_prompt=bool(row["include_in_prompt"]),
        max_chars=int(row["max_chars"]),
        default_value=row["default_value"] or "",
        options=_json_loads(row["options_json"], {}),
    )


def _row_to_table_schema(row: aiosqlite.Row) -> StateTableSchema:
    return StateTableSchema(
        table_id=row["table_id"],
        template_id=row["template_id"],
        table_key=row["table_key"],
        name=row["name"],
        description=row["description"] or "",
        sort_order=int(row["sort_order"]),
        enabled=bool(row["enabled"]),
        required=bool(row["required"]),
        as_status=bool(row["as_status"]),
        include_in_prompt=bool(row["include_in_prompt"]),
        max_prompt_rows=int(row["max_prompt_rows"]),
        prompt_priority=int(row["prompt_priority"]),
        insert_rule=row["insert_rule"] or "",
        update_rule=row["update_rule"] or "",
        delete_rule=row["delete_rule"] or "",
        resolve_rule=row["resolve_rule"] or "",
        note=row["note"] or "",
    )


def _row_to_table_template(row: aiosqlite.Row) -> StateTableTemplate:
    return StateTableTemplate(
        template_id=row["template_id"],
        name=row["name"],
        description=row["description"] or "",
        scenario_type=row["scenario_type"] or "roleplay",
        is_builtin=bool(row["is_builtin"]),
        status=row["status"],
        version=int(row["version"]),
    )


def _row_to_table_cell(row: aiosqlite.Row) -> StateTableCell:
    return StateTableCell(
        cell_id=row["cell_id"],
        row_id=row["row_id"],
        column_id=row["column_id"],
        column_key=row["column_key"],
        value=row["value"] or "",
        confidence=float(row["confidence"]),
        updated_at=row["updated_at"],
    )


def _row_to_table_row(row: aiosqlite.Row) -> StateTableRow:
    return StateTableRow(
        row_id=row["row_id"],
        conversation_id=row["conversation_id"],
        template_id=row["template_id"],
        table_id=row["table_id"],
        table_key=row["table_key"],
        status=row["status"],
        priority=int(row["priority"]),
        confidence=float(row["confidence"]),
        source=row["source"],
        source_turn_id=row["source_turn_id"],
        source_message_ids=_json_loads(row["source_message_ids_json"], []),
        metadata=_json_loads(row["metadata_json"], {}),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class StateTablesMixin:
    async def list_table_templates(self, include_inactive: bool = False) -> list[StateTableTemplate]:
        await self.init_schema()
        where = "" if include_inactive else "WHERE status = 'active'"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM state_table_templates {where} ORDER BY is_builtin DESC, name ASC"
            )
            return [_row_to_table_template(row) for row in await cursor.fetchall()]

    async def get_table_template(self, template_id: str) -> StateTableTemplate | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM state_table_templates WHERE template_id = ?", (template_id,))
            template_row = await cursor.fetchone()
            if not template_row:
                return None
            template = _row_to_table_template(template_row)
            table_cursor = await db.execute(
                """SELECT * FROM state_table_schemas
                   WHERE template_id = ? ORDER BY sort_order ASC, name ASC""",
                (template_id,),
            )
            tables = [_row_to_table_schema(row) for row in await table_cursor.fetchall()]
            for table in tables:
                column_cursor = await db.execute(
                    """SELECT * FROM state_table_columns
                       WHERE table_id = ? ORDER BY sort_order ASC, name ASC""",
                    (table.table_id,),
                )
                table.columns = [_row_to_table_column(row) for row in await column_cursor.fetchall()]
            template.tables = tables
            return template

    async def get_default_table_template(self) -> StateTableTemplate | None:
        return await self.get_table_template("tpl_roleplay_light_tables")

    async def get_conversation_table_template(self, conversation_id: str) -> StateTableTemplate | None:
        config = await self.ensure_conversation_config(conversation_id)
        if config.table_template_id:
            template = await self.get_table_template(config.table_template_id)
            if template:
                return template
        return await self.get_default_table_template()

    async def list_table_rows(
        self,
        conversation_id: str,
        template_id: str | None = None,
        table_key: str | None = None,
        status: str | None = "active",
        limit: int = 500,
    ) -> list[StateTableRow]:
        await self.init_schema()
        where = ["conversation_id = ?"]
        params: list[Any] = [conversation_id]
        if template_id:
            where.append("template_id = ?")
            params.append(template_id)
        if table_key:
            where.append("table_key = ?")
            params.append(table_key)
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = " AND ".join(where)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""SELECT * FROM state_table_rows WHERE {where_sql}
                    ORDER BY priority DESC, updated_at DESC, created_at DESC LIMIT ?""",
                params + [limit],
            )
            rows = [_row_to_table_row(row) for row in await cursor.fetchall()]
            if not rows:
                return []
            row_ids = [row.row_id for row in rows if row.row_id]
            placeholders = ",".join("?" for _ in row_ids)
            cell_cursor = await db.execute(
                f"SELECT * FROM state_table_cells WHERE row_id IN ({placeholders}) ORDER BY updated_at ASC",
                row_ids,
            )
            cells_by_row: dict[str, dict[str, StateTableCell]] = {}
            for cell_row in await cell_cursor.fetchall():
                cell = _row_to_table_cell(cell_row)
                cells_by_row.setdefault(cell.row_id, {})[cell.column_key] = cell
            for row in rows:
                row.cells = cells_by_row.get(row.row_id or "", {})
            return rows

    async def upsert_table_row(self, row: StateTableRow, values: dict[str, Any] | None = None) -> str:
        await self.init_schema()
        row_id = row.row_id or generate_id("state_row_")
        values = values or {key: cell.value for key, cell in row.cells.items()}
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO state_table_rows
                   (row_id, conversation_id, template_id, table_id, table_key, status, priority,
                    confidence, source, source_turn_id, source_message_ids_json, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(row_id) DO UPDATE SET
                    conversation_id = excluded.conversation_id,
                    template_id = excluded.template_id,
                    table_id = excluded.table_id,
                    table_key = excluded.table_key,
                    status = excluded.status,
                    priority = excluded.priority,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    source_turn_id = excluded.source_turn_id,
                    source_message_ids_json = excluded.source_message_ids_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = datetime('now', 'localtime')""",
                (
                    row_id,
                    row.conversation_id,
                    row.template_id,
                    row.table_id,
                    row.table_key,
                    row.status,
                    row.priority,
                    row.confidence,
                    row.source,
                    row.source_turn_id,
                    json.dumps(row.source_message_ids, ensure_ascii=False),
                    json.dumps(row.metadata, ensure_ascii=False),
                ),
            )
            column_ids: dict[str, str | None] = {}
            cursor = await db.execute("SELECT column_key, column_id FROM state_table_columns WHERE table_id = ?", (row.table_id,))
            for column_key, column_id in await cursor.fetchall():
                column_ids[column_key] = column_id
            for column_key, value in values.items():
                cell_id = row.cells.get(column_key).cell_id if column_key in row.cells else generate_id("state_cell_")
                cell_value = "" if value is None else str(value)
                await db.execute(
                    """INSERT INTO state_table_cells (cell_id, row_id, column_id, column_key, value, confidence)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(row_id, column_key) DO UPDATE SET
                        column_id = excluded.column_id,
                        value = excluded.value,
                        confidence = excluded.confidence,
                        updated_at = datetime('now', 'localtime')""",
                    (cell_id, row_id, column_ids.get(column_key), column_key, cell_value, row.confidence),
                )
            await db.commit()
        return row_id

    async def update_table_row_status(self, row_id: str, status: str, reason: str | None = None) -> bool:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT conversation_id, table_key FROM state_table_rows WHERE row_id = ?", (row_id,))
            existing = await cursor.fetchone()
            if not existing:
                return False
            await db.execute(
                "UPDATE state_table_rows SET status = ?, updated_at = datetime('now', 'localtime') WHERE row_id = ?",
                (status, row_id),
            )
            await db.execute(
                """INSERT INTO state_table_events
                   (event_id, conversation_id, event_type, table_key, row_id, reason)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (generate_id("state_evt_"), existing[0], status, existing[1], row_id, reason or ""),
            )
            await db.commit()
            return True

    async def record_table_event(
        self,
        conversation_id: str,
        event_type: str,
        table_key: str | None = None,
        row_id: str | None = None,
        operation: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        turn_id: str | None = None,
        model_output: str | None = None,
    ) -> str:
        await self.init_schema()
        event_id = generate_id("state_evt_")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO state_table_events
                   (event_id, conversation_id, request_id, turn_id, event_type, table_key, row_id,
                    before_json, after_json, operation_json, model_output, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    conversation_id,
                    request_id,
                    turn_id,
                    event_type,
                    table_key,
                    row_id,
                    json.dumps(before or {}, ensure_ascii=False),
                    json.dumps(after or {}, ensure_ascii=False),
                    json.dumps(operation or {}, ensure_ascii=False),
                    model_output,
                    reason or "",
                ),
            )
            await db.commit()
        return event_id
