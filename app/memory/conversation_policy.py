"""Conversation-level memory/state policy definitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


MemoryWritePolicy = Literal["disabled", "candidate", "stable_only", "auto"]
StateUpdatePolicy = Literal["disabled", "manual", "auto"]
InjectionPolicy = Literal["none", "memory_only", "state_only", "state_first", "mixed"]


@dataclass
class ConversationProfile:
    profile_id: str
    name: str
    description: str
    template_id: str | None
    table_template_id: str | None
    mount_preset_id: str | None
    memory_write_policy: str
    state_update_policy: str
    injection_policy: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConversationConfig:
    conversation_id: str
    profile_id: str
    template_id: str | None
    table_template_id: str | None
    mount_preset_id: str | None
    memory_write_policy: str
    state_update_policy: str
    injection_policy: str
    created_from_default: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["created_from_default"] = bool(self.created_from_default)
        return data


DEFAULT_CONVERSATION_PROFILE_ID = "airp_roleplay"


BUILTIN_CONVERSATION_PROFILES: dict[str, ConversationProfile] = {
    "airp_roleplay": ConversationProfile(
        profile_id="airp_roleplay",
        name="普通角色扮演",
        description="适合日常角色扮演、陪伴聊天和稳定关系维护，长期记忆与状态板混合使用。",
        template_id="tpl_roleplay_general",
        table_template_id="tpl_rimtalk_roleplay_tables",
        mount_preset_id=None,
        memory_write_policy="candidate",
        state_update_policy="auto",
        injection_policy="mixed",
    ),
    "rimtalk_colony": ConversationProfile(
        profile_id="rimtalk_colony",
        name="RimTalk / 殖民地模拟",
        description="适合殖民地发展、小人状态、资源与事件追踪，默认只使用状态板以避免污染长期记忆。",
        template_id="tpl_roleplay_general",
        table_template_id="tpl_rimtalk_colony_tables",
        mount_preset_id=None,
        memory_write_policy="disabled",
        state_update_policy="auto",
        injection_policy="state_only",
    ),
    "ttrpg_story": ConversationProfile(
        profile_id="ttrpg_story",
        name="跑团 / 剧情模拟",
        description="适合长线剧情、任务线索、NPC 与阵营关系，状态板优先，仅稳定设定进入长期记忆候选。",
        template_id="tpl_trpg_story",
        table_template_id="tpl_ttrpg_story_tables",
        mount_preset_id=None,
        memory_write_policy="stable_only",
        state_update_policy="auto",
        injection_policy="state_first",
    ),
    "memory_only": ConversationProfile(
        profile_id="memory_only",
        name="长期记忆助手",
        description="适合普通助手或偏好记录，只检索和写入长期记忆，不自动维护状态板。",
        template_id=None,
        table_template_id=None,
        mount_preset_id=None,
        memory_write_policy="candidate",
        state_update_policy="disabled",
        injection_policy="memory_only",
    ),
    "proxy_only": ConversationProfile(
        profile_id="proxy_only",
        name="纯代理",
        description="不注入、不写入长期记忆、不更新状态板，仅作为 OpenAI 兼容代理。",
        template_id=None,
        table_template_id=None,
        mount_preset_id=None,
        memory_write_policy="disabled",
        state_update_policy="disabled",
        injection_policy="none",
    ),
}


def get_profile(profile_id: str | None) -> ConversationProfile:
    return BUILTIN_CONVERSATION_PROFILES.get(profile_id or "", BUILTIN_CONVERSATION_PROFILES[DEFAULT_CONVERSATION_PROFILE_ID])


def list_profiles() -> list[ConversationProfile]:
    return list(BUILTIN_CONVERSATION_PROFILES.values())

