"""Conversation-level memory/state policy definitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

MemoryWritePolicy = Literal["disabled", "candidate", "stable_only", "auto"]
StateUpdatePolicy = Literal["disabled", "manual", "auto"]
InjectionPolicy = Literal["none", "memory_only", "state_only", "state_first", "mixed"]
RetrievalProfileId = Literal["conservative", "balanced", "high_recall", "state_first", "memory_first"]


@dataclass
class RetrievalProfile:
    profile_id: str
    name: str
    description: str
    vector_top_k: int
    final_top_k: int
    max_injected_chars: int
    gate_mode: str
    vector_search_every_n_turns: int
    skip_when_state_is_sufficient: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConversationProfile:
    profile_id: str
    name: str
    description: str
    table_template_id: str | None
    mount_preset_id: str | None
    memory_write_policy: str
    state_update_policy: str
    injection_policy: str
    retrieval_profile_id: str = "balanced"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConversationConfig:
    conversation_id: str
    profile_id: str
    table_template_id: str | None
    mount_preset_id: str | None
    memory_write_policy: str
    state_update_policy: str
    injection_policy: str
    retrieval_profile_id: str = "balanced"
    created_from_default: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["created_from_default"] = bool(self.created_from_default)
        return data


DEFAULT_CONVERSATION_PROFILE_ID = "airp_roleplay"
DEFAULT_RETRIEVAL_PROFILE_ID = "balanced"


BUILTIN_RETRIEVAL_PROFILES: dict[str, RetrievalProfile] = {
    "conservative": RetrievalProfile(
        profile_id="conservative",
        name="保守召回",
        description="减少注入和周期检索，优先降低跨角色或跨世界污染。",
        vector_top_k=16,
        final_top_k=4,
        max_injected_chars=1000,
        gate_mode="auto",
        vector_search_every_n_turns=8,
        skip_when_state_is_sufficient=True,
    ),
    "balanced": RetrievalProfile(
        profile_id="balanced",
        name="平衡召回",
        description="默认策略，保持当前召回规模和门控行为。",
        vector_top_k=30,
        final_top_k=6,
        max_injected_chars=1500,
        gate_mode="auto",
        vector_search_every_n_turns=6,
        skip_when_state_is_sufficient=True,
    ),
    "high_recall": RetrievalProfile(
        profile_id="high_recall",
        name="高召回",
        description="扩大候选和注入数量，适合长剧情回顾或资料密集会话。",
        vector_top_k=50,
        final_top_k=10,
        max_injected_chars=2200,
        gate_mode="auto",
        vector_search_every_n_turns=3,
        skip_when_state_is_sufficient=False,
    ),
    "state_first": RetrievalProfile(
        profile_id="state_first",
        name="状态板优先",
        description="长期记忆只补充关键事实，主要依赖状态板保持连续性。",
        vector_top_k=20,
        final_top_k=4,
        max_injected_chars=900,
        gate_mode="auto",
        vector_search_every_n_turns=8,
        skip_when_state_is_sufficient=True,
    ),
    "memory_first": RetrievalProfile(
        profile_id="memory_first",
        name="记忆优先",
        description="优先注入长期记忆，适合偏好、设定和历史事实密集的会话。",
        vector_top_k=40,
        final_top_k=8,
        max_injected_chars=2000,
        gate_mode="auto",
        vector_search_every_n_turns=4,
        skip_when_state_is_sufficient=False,
    ),
}


BUILTIN_CONVERSATION_PROFILES: dict[str, ConversationProfile] = {
    "airp_roleplay": ConversationProfile(
        profile_id="airp_roleplay",
        name="普通角色扮演",
        description="适合日常角色扮演、陪伴聊天和稳定关系维护，长期记忆与状态板混合使用。",
        table_template_id="tpl_roleplay_light_tables",
        mount_preset_id=None,
        memory_write_policy="candidate",
        state_update_policy="auto",
        injection_policy="mixed",
    ),
    "rimtalk_colony": ConversationProfile(
        profile_id="rimtalk_colony",
        name="RimTalk / 殖民地模拟",
        description="适合殖民地发展、小人状态、资源与事件追踪，默认只使用状态板以避免污染长期记忆。",
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


def get_retrieval_profile(profile_id: str | None) -> RetrievalProfile:
    return BUILTIN_RETRIEVAL_PROFILES.get(profile_id or "", BUILTIN_RETRIEVAL_PROFILES[DEFAULT_RETRIEVAL_PROFILE_ID])


def list_retrieval_profiles() -> list[RetrievalProfile]:
    return list(BUILTIN_RETRIEVAL_PROFILES.values())

