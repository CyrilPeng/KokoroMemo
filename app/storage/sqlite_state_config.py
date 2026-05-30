"""Conversation policy config methods for SQLiteStateStore."""

from __future__ import annotations

from typing import Any

import aiosqlite

from app.core.ids import generate_id
from app.memory.conversation_policy import (
    DEFAULT_CONVERSATION_PROFILE_ID,
    ConversationConfig,
    ConversationProfile,
    get_profile,
)


def _row_to_conversation_config(row: aiosqlite.Row) -> ConversationConfig:
    return ConversationConfig(
        conversation_id=row["conversation_id"],
        profile_id=row["profile_id"],
        table_template_id=row["table_template_id"],
        mount_preset_id=row["mount_preset_id"],
        memory_write_policy=row["memory_write_policy"],
        state_update_policy=row["state_update_policy"],
        injection_policy=row["injection_policy"],
        retrieval_profile_id=row["retrieval_profile_id"],
        created_from_default=bool(row["created_from_default"]),
        updated_at=row["updated_at"],
    )


class ConversationConfigMixin:
    async def list_custom_conversation_profiles(self, include_inactive: bool = False) -> list[ConversationProfile]:
        await self.init_schema()
        where = "" if include_inactive else "WHERE status = 'active'"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(f"SELECT * FROM conversation_profiles {where} ORDER BY updated_at DESC, name ASC")
            rows = await cursor.fetchall()
        return [
            ConversationProfile(
                profile_id=row["profile_id"],
                name=row["name"],
                description=row["description"] or "",
                table_template_id=row["table_template_id"],
                mount_preset_id=row["mount_preset_id"],
                memory_write_policy=row["memory_write_policy"],
                state_update_policy=row["state_update_policy"],
                injection_policy=row["injection_policy"],
                retrieval_profile_id=row["retrieval_profile_id"],
            )
            for row in rows
        ]

    async def upsert_custom_conversation_profile(self, data: dict[str, Any]) -> ConversationProfile:
        await self.init_schema()
        profile_id = data.get("profile_id") or generate_id("profile_")
        name = data.get("name") or "未命名会话方案"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_profiles
                   (profile_id, name, description, table_template_id, mount_preset_id,
                    memory_write_policy, state_update_policy, injection_policy, retrieval_profile_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                   ON CONFLICT(profile_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    table_template_id = excluded.table_template_id,
                    mount_preset_id = excluded.mount_preset_id,
                    memory_write_policy = excluded.memory_write_policy,
                    state_update_policy = excluded.state_update_policy,
                    injection_policy = excluded.injection_policy,
                    retrieval_profile_id = excluded.retrieval_profile_id,
                    status = 'active',
                    updated_at = datetime('now', 'localtime')""",
                (
                    profile_id,
                    name,
                    data.get("description", ""),
                    data.get("table_template_id"),
                    data.get("mount_preset_id"),
                    data.get("memory_write_policy") or "candidate",
                    data.get("state_update_policy") or "auto",
                    data.get("injection_policy") or "mixed",
                    data.get("retrieval_profile_id") or "balanced",
                ),
            )
            await db.commit()
        return ConversationProfile(
            profile_id=profile_id,
            name=name,
            description=data.get("description", ""),
            table_template_id=data.get("table_template_id"),
            mount_preset_id=data.get("mount_preset_id"),
            memory_write_policy=data.get("memory_write_policy") or "candidate",
            state_update_policy=data.get("state_update_policy") or "auto",
            injection_policy=data.get("injection_policy") or "mixed",
            retrieval_profile_id=data.get("retrieval_profile_id") or "balanced",
        )

    async def delete_custom_conversation_profile(self, profile_id: str) -> bool:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE conversation_profiles SET status = 'deleted', updated_at = datetime('now', 'localtime') WHERE profile_id = ?",
                (profile_id,),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_default_conversation_config(self) -> ConversationConfig:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM conversation_default_config WHERE id = 'global'")
            row = await cursor.fetchone()
        if row:
            return ConversationConfig(
                conversation_id="__default__",
                profile_id=row["profile_id"],
                table_template_id=row["table_template_id"],
                mount_preset_id=row["mount_preset_id"],
                memory_write_policy=row["memory_write_policy"],
                state_update_policy=row["state_update_policy"],
                injection_policy=row["injection_policy"],
                retrieval_profile_id=row["retrieval_profile_id"],
                created_from_default=True,
                updated_at=row["updated_at"],
            )
        profile = get_profile(DEFAULT_CONVERSATION_PROFILE_ID)
        return ConversationConfig(
            conversation_id="__default__",
            profile_id=profile.profile_id,
            table_template_id=profile.table_template_id,
            mount_preset_id=profile.mount_preset_id,
            memory_write_policy=profile.memory_write_policy,
            state_update_policy=profile.state_update_policy,
            injection_policy=profile.injection_policy,
            retrieval_profile_id=profile.retrieval_profile_id,
            created_from_default=True,
        )

    async def set_default_conversation_config(self, data: ConversationConfig | dict[str, Any]) -> ConversationConfig:
        await self.init_schema()
        payload = data.to_dict() if isinstance(data, ConversationConfig) else dict(data)
        profile = get_profile(payload.get("profile_id"))
        profile_id = payload.get("profile_id") or profile.profile_id
        table_template_id = payload.get("table_template_id", profile.table_template_id)
        mount_preset_id = payload.get("mount_preset_id", profile.mount_preset_id)
        memory_write_policy = payload.get("memory_write_policy") or profile.memory_write_policy
        state_update_policy = payload.get("state_update_policy") or profile.state_update_policy
        injection_policy = payload.get("injection_policy") or profile.injection_policy
        retrieval_profile_id = payload.get("retrieval_profile_id") or profile.retrieval_profile_id
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_default_config
                   (id, profile_id, table_template_id, mount_preset_id,
                    memory_write_policy, state_update_policy, injection_policy, retrieval_profile_id)
                   VALUES ('global', ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    table_template_id = excluded.table_template_id,
                    mount_preset_id = excluded.mount_preset_id,
                    memory_write_policy = excluded.memory_write_policy,
                    state_update_policy = excluded.state_update_policy,
                    injection_policy = excluded.injection_policy,
                    retrieval_profile_id = excluded.retrieval_profile_id,
                    updated_at = datetime('now', 'localtime')""",
                (
                    profile_id,
                    table_template_id,
                    mount_preset_id,
                    memory_write_policy,
                    state_update_policy,
                    injection_policy,
                    retrieval_profile_id,
                ),
            )
            await db.commit()
        return await self.get_default_conversation_config()

    async def get_conversation_config(self, conversation_id: str) -> ConversationConfig | None:
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM conversation_configs WHERE conversation_id = ?", (conversation_id,)
            )
            row = await cursor.fetchone()
        return _row_to_conversation_config(row) if row else None

    async def set_conversation_config(self, config: ConversationConfig | dict[str, Any]) -> ConversationConfig:
        await self.init_schema()
        payload = config.to_dict() if isinstance(config, ConversationConfig) else dict(config)
        conversation_id = payload.get("conversation_id")
        if not conversation_id:
            raise ValueError("conversation_id is required")
        profile = get_profile(payload.get("profile_id"))
        profile_id = payload.get("profile_id") or profile.profile_id
        table_template_id = payload.get("table_template_id", profile.table_template_id)
        mount_preset_id = payload.get("mount_preset_id", profile.mount_preset_id)
        memory_write_policy = payload.get("memory_write_policy") or profile.memory_write_policy
        state_update_policy = payload.get("state_update_policy") or profile.state_update_policy
        injection_policy = payload.get("injection_policy") or profile.injection_policy
        retrieval_profile_id = payload.get("retrieval_profile_id") or profile.retrieval_profile_id
        created_from_default = 1 if payload.get("created_from_default") else 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_configs
                   (conversation_id, profile_id, table_template_id, mount_preset_id,
                    memory_write_policy, state_update_policy, injection_policy, retrieval_profile_id, created_from_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(conversation_id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    table_template_id = excluded.table_template_id,
                    mount_preset_id = excluded.mount_preset_id,
                    memory_write_policy = excluded.memory_write_policy,
                    state_update_policy = excluded.state_update_policy,
                    injection_policy = excluded.injection_policy,
                    retrieval_profile_id = excluded.retrieval_profile_id,
                    updated_at = datetime('now', 'localtime')""",
                (
                    conversation_id,
                    profile_id,
                    table_template_id,
                    mount_preset_id,
                    memory_write_policy,
                    state_update_policy,
                    injection_policy,
                    retrieval_profile_id,
                    created_from_default,
                ),
            )
            await db.commit()
        saved = await self.get_conversation_config(conversation_id)
        if not saved:
            raise RuntimeError("failed to save conversation config")
        return saved

    async def ensure_conversation_config(self, conversation_id: str) -> ConversationConfig:
        existing = await self.get_conversation_config(conversation_id)
        if existing:
            return existing
        default = await self.get_default_conversation_config()
        return await self.set_conversation_config(
            ConversationConfig(
                conversation_id=conversation_id,
                profile_id=default.profile_id,
                table_template_id=default.table_template_id,
                mount_preset_id=default.mount_preset_id,
                memory_write_policy=default.memory_write_policy,
                state_update_policy=default.state_update_policy,
                injection_policy=default.injection_policy,
                retrieval_profile_id=default.retrieval_profile_id,
                created_from_default=True,
            )
        )

    async def update_conversation_character_refs(
        self, conversation_id: str, character_id: str | None
    ) -> dict[str, int]:
        """更新单个会话状态数据中的角色引用。"""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            items = await db.execute(
                "UPDATE conversation_state_items SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE conversation_id = ?",
                (character_id, conversation_id),
            )
            await db.commit()
            return {"items": items.rowcount}

    async def merge_character_refs(self, source_character_id: str, target_character_id: str) -> dict[str, int]:
        """将状态板数据中的源角色引用迁移到目标角色。"""
        await self.init_schema()
        async with aiosqlite.connect(self.db_path) as db:
            items = await db.execute(
                "UPDATE conversation_state_items SET character_id = ?, updated_at = datetime('now', 'localtime') WHERE character_id = ?",
                (target_character_id, source_character_id),
            )
            await db.commit()
            return {"items": items.rowcount}

        async def update_conversation_character_refs(
            self, conversation_id: str, character_id: str | None
        ) -> dict[str, int]:
            await self.init_schema()
            return {"state_table_rows": 0}

        async def merge_character_refs(self, source_character_id: str, target_character_id: str) -> dict[str, int]:
            await self.init_schema()
            return {"state_table_rows": 0}
