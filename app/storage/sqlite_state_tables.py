"""State table template, row and event methods for SQLiteStateStore."""

from __future__ import annotations

import json
import re
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


def _slugify_key(value: str, prefix: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip().lower()).strip("_")
    return key or f"{prefix}_{generate_id('')[:8]}"


class StateTablesMixin:
    async def list_table_templates(self, include_inactive: bool = False) -> list[StateTableTemplate]:
        await self.init_schema()
        where = "" if include_inactive else "WHERE status = 'active'"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(f"SELECT * FROM state_table_templates {where} ORDER BY is_builtin DESC, name ASC")
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

    async def save_table_template(self, template: StateTableTemplate) -> StateTableTemplate:
        await self.init_schema()
        template_id = template.template_id or generate_id("tpl_custom_")
        async with aiosqlite.connect(self.db_path) as db:
            existing_cursor = await db.execute(
                "SELECT is_builtin FROM state_table_templates WHERE template_id = ?", (template_id,)
            )
            existing = await existing_cursor.fetchone()
            if existing and int(existing[0]) == 1:
                raise ValueError("builtin templates cannot be overwritten")
            await db.execute(
                """INSERT INTO state_table_templates
                   (template_id, name, description, scenario_type, is_builtin, status, version)
                   VALUES (?, ?, ?, ?, 0, ?, ?)
                   ON CONFLICT(template_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    scenario_type = excluded.scenario_type,
                    status = excluded.status,
                    version = state_table_templates.version + 1,
                    updated_at = datetime('now', 'localtime')""",
                (
                    template_id,
                    template.name,
                    template.description,
                    template.scenario_type,
                    template.status,
                    template.version,
                ),
            )
            keep_table_ids = [
                table.table_id or f"{template_id}__{_slugify_key(table.table_key or table.name, 'tab')}"
                for table in template.tables
            ]
            if keep_table_ids:
                placeholders = ",".join("?" for _ in keep_table_ids)
                await db.execute(
                    f"DELETE FROM state_table_columns WHERE table_id IN (SELECT table_id FROM state_table_schemas WHERE template_id = ? AND table_id NOT IN ({placeholders}))",
                    (template_id, *keep_table_ids),
                )
                await db.execute(
                    f"DELETE FROM state_table_schemas WHERE template_id = ? AND table_id NOT IN ({placeholders})",
                    (template_id, *keep_table_ids),
                )
            for table_index, table in enumerate(template.tables):
                table_key = _slugify_key(table.table_key or table.name, "tab")
                table_id = table.table_id or f"{template_id}__{table_key}"
                keep_column_ids = [
                    column.column_id or f"{table_id}__{_slugify_key(column.column_key or column.name, 'col')}"
                    for column in table.columns
                ]
                if keep_column_ids:
                    placeholders = ",".join("?" for _ in keep_column_ids)
                    await db.execute(
                        f"DELETE FROM state_table_columns WHERE table_id = ? AND column_id NOT IN ({placeholders})",
                        (table_id, *keep_column_ids),
                    )
                await db.execute(
                    """INSERT INTO state_table_schemas
                       (table_id, template_id, table_key, name, description, sort_order,
                        enabled, required, as_status, include_in_prompt, max_prompt_rows,
                        prompt_priority, insert_rule, update_rule, delete_rule, resolve_rule, note)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(table_id) DO UPDATE SET
                        table_key = excluded.table_key,
                        name = excluded.name,
                        description = excluded.description,
                        sort_order = excluded.sort_order,
                        enabled = excluded.enabled,
                        required = excluded.required,
                        as_status = excluded.as_status,
                        include_in_prompt = excluded.include_in_prompt,
                        max_prompt_rows = excluded.max_prompt_rows,
                        prompt_priority = excluded.prompt_priority,
                        insert_rule = excluded.insert_rule,
                        update_rule = excluded.update_rule,
                        delete_rule = excluded.delete_rule,
                        resolve_rule = excluded.resolve_rule,
                        note = excluded.note,
                        updated_at = datetime('now', 'localtime')""",
                    (
                        table_id,
                        template_id,
                        table_key,
                        table.name,
                        table.description,
                        table.sort_order if table.sort_order is not None else table_index,
                        int(table.enabled),
                        int(table.required),
                        int(table.as_status),
                        int(table.include_in_prompt),
                        int(table.max_prompt_rows),
                        int(table.prompt_priority),
                        table.insert_rule,
                        table.update_rule,
                        table.delete_rule,
                        table.resolve_rule,
                        table.note,
                    ),
                )
                for column_index, column in enumerate(table.columns):
                    column_key = _slugify_key(column.column_key or column.name, "col")
                    column_id = column.column_id or f"{table_id}__{column_key}"
                    await db.execute(
                        """INSERT INTO state_table_columns
                           (column_id, table_id, column_key, name, description, value_type,
                            required, sort_order, include_in_prompt, max_chars, default_value, options_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(column_id) DO UPDATE SET
                            column_key = excluded.column_key,
                            name = excluded.name,
                            description = excluded.description,
                            value_type = excluded.value_type,
                            required = excluded.required,
                            sort_order = excluded.sort_order,
                            include_in_prompt = excluded.include_in_prompt,
                            max_chars = excluded.max_chars,
                            default_value = excluded.default_value,
                            options_json = excluded.options_json,
                            updated_at = datetime('now', 'localtime')""",
                        (
                            column_id,
                            table_id,
                            column_key,
                            column.name,
                            column.description,
                            column.value_type,
                            int(column.required),
                            column.sort_order if column.sort_order is not None else column_index,
                            int(column.include_in_prompt),
                            int(column.max_chars),
                            column.default_value,
                            json.dumps(column.options or {}, ensure_ascii=False),
                        ),
                    )
            await db.commit()
        saved = await self.get_table_template(template_id)
        if not saved:
            raise RuntimeError("failed to save state table template")
        return saved

    async def clone_table_template(self, source_template_id: str, name: str | None = None) -> StateTableTemplate:
        source = await self.get_table_template(source_template_id)
        if not source:
            raise ValueError("source template not found")
        template_id = generate_id("tpl_custom_")
        source.template_id = template_id
        source.name = name or f"{source.name} ??"
        source.is_builtin = False
        source.version = 1
        for table in source.tables:
            old_table_key = table.table_key
            table.table_id = f"{template_id}__{old_table_key}"
            table.template_id = template_id
            for column in table.columns:
                column.table_id = table.table_id
                column.column_id = f"{table.table_id}__{column.column_key}"
        return await self.save_table_template(source)

    async def add_table_to_template(self, template_id: str, data: dict[str, Any]) -> StateTableTemplate:
        template = await self.get_table_template(template_id)
        if not template:
            raise ValueError("template not found")
        if template.is_builtin:
            template = await self.clone_table_template(template_id, f"{template.name} 自定义")
            template_id = template.template_id or template_id
        table_key = _slugify_key(data.get("table_key") or data.get("name"), "tab")
        if any(table.table_key == table_key for table in template.tables):
            raise ValueError("table_key already exists")
        table = StateTableSchema(
            table_id=f"{template_id}__{table_key}",
            template_id=template_id,
            table_key=table_key,
            name=data.get("name") or table_key,
            description=data.get("description", ""),
            sort_order=len(template.tables),
            max_prompt_rows=int(data.get("max_prompt_rows", 4)),
            prompt_priority=int(data.get("prompt_priority", 50)),
            columns=[
                StateTableColumn(
                    column_id=None,
                    table_id=f"{template_id}__{table_key}",
                    column_key=table_key,
                    name=data.get("name") or table_key,
                    description=data.get("description", ""),
                    required=True,
                    sort_order=0,
                    max_chars=360,
                ),
            ],
        )
        template.tables.append(table)
        return await self.save_table_template(template)

    async def add_column_to_table(self, template_id: str, table_key: str, data: dict[str, Any]) -> StateTableTemplate:
        template = await self.get_table_template(template_id)
        if not template:
            raise ValueError("template not found")
        if template.is_builtin:
            template = await self.clone_table_template(template_id, f"{template.name} 自定义")
            template_id = template.template_id or template_id
        table = next((item for item in template.tables if item.table_key == table_key), None)
        if not table:
            raise ValueError("table not found")
        column_key = _slugify_key(data.get("column_key") or data.get("name"), "col")
        if any(column.column_key == column_key for column in table.columns):
            raise ValueError("column_key already exists")
        table.columns.append(
            StateTableColumn(
                column_id=None,
                table_id=table.table_id or f"{template_id}__{table.table_key}",
                column_key=column_key,
                name=data.get("name") or column_key,
                description=data.get("description", ""),
                required=bool(data.get("required", False)),
                sort_order=len(table.columns),
                include_in_prompt=bool(data.get("include_in_prompt", True)),
                max_chars=int(data.get("max_chars", 240)),
            )
        )
        return await self.save_table_template(template)

    async def update_table_in_template(
        self, template_id: str, table_key: str, data: dict[str, Any]
    ) -> StateTableTemplate:
        template = await self.get_table_template(template_id)
        if not template:
            raise ValueError("template not found")
        if template.is_builtin:
            raise ValueError("builtin templates cannot be modified; clone it first")
        table = next((item for item in template.tables if item.table_key == table_key), None)
        if not table:
            raise ValueError("table not found")
        if "name" in data and str(data.get("name") or "").strip():
            table.name = str(data["name"]).strip()
        if "description" in data:
            table.description = str(data.get("description") or "")
        if "max_prompt_rows" in data:
            table.max_prompt_rows = int(data.get("max_prompt_rows") or table.max_prompt_rows)
        if "prompt_priority" in data:
            table.prompt_priority = int(data.get("prompt_priority") or table.prompt_priority)
        return await self.save_table_template(template)

    async def delete_table_from_template(self, template_id: str, table_key: str) -> StateTableTemplate:
        template = await self.get_table_template(template_id)
        if not template:
            raise ValueError("template not found")
        if template.is_builtin:
            raise ValueError("builtin templates cannot be modified; clone it first")
        table = next((item for item in template.tables if item.table_key == table_key), None)
        if not table:
            raise ValueError("table not found")
        if len(template.tables) <= 1:
            raise ValueError("template must keep at least one table")
        template.tables = [item for item in template.tables if item.table_key != table_key]
        for index, item in enumerate(template.tables):
            item.sort_order = index
        return await self.save_table_template(template)

    async def update_column_in_table(
        self, template_id: str, table_key: str, column_key: str, data: dict[str, Any]
    ) -> StateTableTemplate:
        template = await self.get_table_template(template_id)
        if not template:
            raise ValueError("template not found")
        if template.is_builtin:
            raise ValueError("builtin templates cannot be modified; clone it first")
        table = next((item for item in template.tables if item.table_key == table_key), None)
        if not table:
            raise ValueError("table not found")
        column = next((item for item in table.columns if item.column_key == column_key), None)
        if not column:
            raise ValueError("column not found")
        if "name" in data and str(data.get("name") or "").strip():
            column.name = str(data["name"]).strip()
        if "description" in data:
            column.description = str(data.get("description") or "")
        if "required" in data:
            column.required = bool(data.get("required"))
        if "include_in_prompt" in data:
            column.include_in_prompt = bool(data.get("include_in_prompt"))
        if "max_chars" in data:
            column.max_chars = int(data.get("max_chars") or column.max_chars)
        return await self.save_table_template(template)

    async def delete_table_template(self, template_id: str) -> bool:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT is_builtin FROM state_table_templates WHERE template_id = ? AND status = 'active'",
                (template_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return False
            if int(row[0]) == 1:
                raise ValueError("builtin templates cannot be deleted")
            await db.execute(
                "UPDATE state_table_templates SET status = 'deleted', updated_at = datetime('now', 'localtime') WHERE template_id = ?",
                (template_id,),
            )
            await db.execute(
                "UPDATE conversation_configs SET table_template_id = NULL WHERE table_template_id = ?",
                (template_id,),
            )
            await db.commit()
            return True

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
            cursor = await db.execute(
                "SELECT column_key, column_id FROM state_table_columns WHERE table_id = ?", (row.table_id,)
            )
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

    async def update_single_cell(self, row_id: str, column_key: str, value: str) -> dict[str, Any] | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT conversation_id, table_key, table_id FROM state_table_rows WHERE row_id = ?",
                (row_id,),
            )
            row_info = await cursor.fetchone()
            if not row_info:
                return None
            old_cursor = await db.execute(
                "SELECT value FROM state_table_cells WHERE row_id = ? AND column_key = ?",
                (row_id, column_key),
            )
            old_row = await old_cursor.fetchone()
            old_value = old_row["value"] if old_row else ""
            col_cursor = await db.execute(
                "SELECT column_id FROM state_table_columns WHERE table_id = ? AND column_key = ?",
                (row_info["table_id"], column_key),
            )
            col_row = await col_cursor.fetchone()
            column_id = col_row["column_id"] if col_row else None
            cell_id = generate_id("state_cell_")
            cell_value = "" if value is None else str(value)
            await db.execute(
                """INSERT INTO state_table_cells (cell_id, row_id, column_id, column_key, value, confidence)
                   VALUES (?, ?, ?, ?, ?, 1.0)
                   ON CONFLICT(row_id, column_key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = datetime('now', 'localtime')""",
                (cell_id, row_id, column_id, column_key, cell_value),
            )
            await db.execute(
                "UPDATE state_table_rows SET updated_at = datetime('now', 'localtime') WHERE row_id = ?",
                (row_id,),
            )
            await db.commit()
            cell_cursor = await db.execute(
                "SELECT cell_id, value, confidence, updated_at FROM state_table_cells WHERE row_id = ? AND column_key = ?",
                (row_id, column_key),
            )
            cell = await cell_cursor.fetchone()
        conversation_id = row_info["conversation_id"]
        table_key = row_info["table_key"]
        await self.record_table_event(
            conversation_id,
            "manual_cell_edit",
            table_key=table_key,
            row_id=row_id,
            before={column_key: old_value},
            after={column_key: cell_value},
        )
        return (
            {
                "cell_id": cell["cell_id"],
                "column_key": column_key,
                "value": cell["value"],
                "confidence": cell["confidence"],
                "updated_at": cell["updated_at"],
            }
            if cell
            else None
        )

    async def update_table_row_status(self, row_id: str, status: str, reason: str | None = None) -> bool:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT conversation_id, table_key FROM state_table_rows WHERE row_id = ?", (row_id,)
            )
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

    async def list_table_events(
        self,
        conversation_id: str,
        turn_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        await self.init_schema()
        where = ["conversation_id = ?"]
        params: list[Any] = [conversation_id]
        if turn_id:
            where.append("turn_id = ?")
            params.append(turn_id)
        where_sql = " AND ".join(where)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM state_table_events WHERE {where_sql} ORDER BY created_at DESC LIMIT ?",
                params + [limit],
            )
            events = []
            for row in await cursor.fetchall():
                events.append(
                    {
                        "event_id": row["event_id"],
                        "event_type": row["event_type"],
                        "table_key": row["table_key"],
                        "row_id": row["row_id"],
                        "before": json.loads(row["before_json"]) if row["before_json"] else None,
                        "after": json.loads(row["after_json"]) if row["after_json"] else None,
                        "reason": row["reason"],
                        "turn_id": row["turn_id"],
                        "created_at": row["created_at"],
                    }
                )
            return events

    async def revert_table_events(self, conversation_id: str, event_ids: list[str]) -> int:
        await self.init_schema()
        reverted = 0
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            for event_id in event_ids:
                cursor = await db.execute(
                    "SELECT * FROM state_table_events WHERE event_id = ? AND conversation_id = ?",
                    (event_id, conversation_id),
                )
                event = await cursor.fetchone()
                if not event:
                    continue
                event_type = event["event_type"]
                row_id = event["row_id"]
                before_json = event["before_json"]
                if not row_id:
                    continue
                if event_type == "insert_row":
                    await db.execute(
                        "UPDATE state_table_rows SET status = 'resolved', updated_at = datetime('now', 'localtime') WHERE row_id = ?",
                        (row_id,),
                    )
                elif event_type in {"update_row", "manual_cell_edit", "manual_upsert_row"}:
                    before = json.loads(before_json) if before_json else {}
                    if before:
                        for col_key, value in before.items():
                            await db.execute(
                                """UPDATE state_table_cells SET value = ?, updated_at = datetime('now', 'localtime')
                                   WHERE row_id = ? AND column_key = ?""",
                                (str(value), row_id, col_key),
                            )
                        await db.execute(
                            "UPDATE state_table_rows SET updated_at = datetime('now', 'localtime') WHERE row_id = ?",
                            (row_id,),
                        )
                elif event_type in {"delete_row", "resolve_row", "resolved"}:
                    await db.execute(
                        "UPDATE state_table_rows SET status = 'active', updated_at = datetime('now', 'localtime') WHERE row_id = ?",
                        (row_id,),
                    )
                else:
                    continue
                reverted += 1
            await db.commit()
        if reverted > 0:
            await self.record_table_event(
                conversation_id,
                "revert",
                reason=f"Reverted {reverted} events",
            )
        return reverted

    async def batch_update_rows(self, row_ids: list[str], action: str, value: Any = None) -> int:
        await self.init_schema()
        if not row_ids:
            return 0
        affected = 0
        async with aiosqlite.connect(self.db_path) as db:
            placeholders = ",".join("?" for _ in row_ids)
            if action == "delete":
                cursor = await db.execute(
                    f"UPDATE state_table_rows SET status = 'resolved', updated_at = datetime('now', 'localtime') WHERE row_id IN ({placeholders})",
                    row_ids,
                )
                affected = cursor.rowcount
            elif action == "set_priority":
                cursor = await db.execute(
                    f"UPDATE state_table_rows SET priority = ?, updated_at = datetime('now', 'localtime') WHERE row_id IN ({placeholders})",
                    [int(value or 50)] + row_ids,
                )
                affected = cursor.rowcount
            elif action == "set_status":
                cursor = await db.execute(
                    f"UPDATE state_table_rows SET status = ?, updated_at = datetime('now', 'localtime') WHERE row_id IN ({placeholders})",
                    [str(value or "active")] + row_ids,
                )
                affected = cursor.rowcount
            await db.commit()
        return affected

    async def get_cell_history(self, row_id: str, column_key: str, limit: int = 20) -> list[dict[str, Any]]:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT event_id, event_type, before_json, after_json, reason, turn_id, created_at
                   FROM state_table_events
                   WHERE row_id = ? AND (before_json LIKE ? OR after_json LIKE ?)
                   ORDER BY created_at DESC LIMIT ?""",
                (row_id, f'%"{column_key}"%', f'%"{column_key}"%', limit),
            )
            history: list[dict[str, Any]] = []
            for row in await cursor.fetchall():
                before = json.loads(row["before_json"]) if row["before_json"] else {}
                after = json.loads(row["after_json"]) if row["after_json"] else {}
                if column_key not in before and column_key not in after:
                    continue
                history.append(
                    {
                        "event_id": row["event_id"],
                        "event_type": row["event_type"],
                        "old_value": before.get(column_key),
                        "new_value": after.get(column_key),
                        "reason": row["reason"],
                        "turn_id": row["turn_id"],
                        "created_at": row["created_at"],
                    }
                )
            return history
