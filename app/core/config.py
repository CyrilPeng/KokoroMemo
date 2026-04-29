"""Configuration loading and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 14514
    webui_port: int = 14515
    log_level: str = "INFO"
    allow_remote_access: bool = False
    admin_token_env: str = "ADMIN_TOKEN"
    admin_token: str = ""
    timezone: str = ""

    def get_admin_token(self) -> str:
        if self.admin_token:
            return self.admin_token
        return os.environ.get(self.admin_token_env, "")


@dataclass
class LLMConfig:
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key_env: str = "LLM_API_KEY"
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 120
    forward_mode: str = "override"  # "override" = 用本项目配置, "passthrough" = 透传客户端的 Key 和 Model

    def get_api_key(self) -> str:
        """Get API key: direct value takes priority over env var."""
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")


@dataclass
class EmbeddingConfig:
    enabled: bool = True
    provider: str = "modelark"
    base_url: str = "https://ai.gitee.com/v1"
    api_key: str = ""
    api_key_env: str = "MODELARK_API_KEY"
    model: str = "qwen3-embedding-8b"
    dimension: int = 4096
    timeout_seconds: int = 8
    batch_size: int = 16
    normalize: bool = True

    def get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")


@dataclass
class RerankConfig:
    enabled: bool = False
    provider: str = "modelark"
    base_url: str = "https://ai.gitee.com/v1"
    api_key: str = ""
    api_key_env: str = "MODELARK_API_KEY"
    model: str = "qwen3-reranker-8b"
    timeout_seconds: int = 8
    candidate_top_k: int = 30
    final_top_k: int = 8
    max_documents_per_request: int = 20

    def get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")


@dataclass
class ScoringConfig:
    vector_weight: float = 0.55
    importance_weight: float = 0.20
    recency_weight: float = 0.10
    scope_weight: float = 0.10
    confidence_weight: float = 0.05


@dataclass
class ExtractionConfig:
    min_importance: float = 0.45
    min_confidence: float = 0.55
    extract_after_each_turn: bool = True
    fallback_rule_based: bool = True


@dataclass
class ScopesConfig:
    include_global: bool = True
    include_character: bool = True
    include_conversation: bool = True


@dataclass
class HotContextConfig:
    enabled: bool = True
    inject_always: bool = True
    max_chars: int = 1200
    include_sections: dict[str, bool] = field(default_factory=lambda: {
        "scene": True,
        "key_person": True,
        "main_quest": True,
        "side_quest": True,
        "promise": True,
        "open_loop": True,
        "relationship": True,
        "boundary": True,
        "preference": True,
        "location": True,
        "item": True,
        "world_state": True,
        "recent_summary": True,
        "mood": True,
    })
    section_order: list[str] = field(default_factory=lambda: [
        "boundary",
        "scene",
        "location",
        "key_person",
        "relationship",
        "main_quest",
        "side_quest",
        "promise",
        "open_loop",
        "item",
        "world_state",
        "recent_summary",
        "mood",
        "preference",
    ])
    max_items_per_section: dict[str, int] = field(default_factory=lambda: {
        "boundary": 5,
        "scene": 6,
        "location": 4,
        "key_person": 8,
        "relationship": 4,
        "main_quest": 5,
        "side_quest": 5,
        "promise": 6,
        "open_loop": 6,
        "item": 6,
        "world_state": 5,
        "recent_summary": 3,
        "mood": 3,
        "preference": 5,
    })


@dataclass
class StateUpdaterConfig:
    enabled: bool = True
    mode: str = "model_template"
    update_after_each_turn: bool = True
    update_every_n_turns: int = 1
    min_confidence: float = 0.55
    auto_expire_resolved_items: bool = True
    max_state_items_per_conversation: int = 200
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    api_key_env: str = "STATE_FILLER_API_KEY"
    model: str = ""
    timeout_seconds: int = 30
    temperature: float = 0.0
    prompt: str = ""

    def get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")


@dataclass
class MemoryJudgeConfig:
    enabled: bool = True
    provider: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    api_key_env: str = "MEMORY_JUDGE_API_KEY"
    model: str = ""
    timeout_seconds: int = 30
    temperature: float = 0.0
    mode: str = "model_only"
    user_rules: list[str] = field(default_factory=list)
    prompt: str = ""

    def get_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.api_key_env, "")


@dataclass
class RetrievalGateConfig:
    enabled: bool = True
    mode: str = "auto"
    vector_search_on_new_session: bool = True
    vector_search_every_n_turns: int = 6
    vector_search_when_state_confidence_below: float = 0.65
    trigger_keywords: list[str] = field(default_factory=lambda: [
        "记得",
        "还记得",
        "上次",
        "以前",
        "之前",
        "曾经",
        "约定",
        "我们说过",
        "你答应过",
        "那个人",
        "那个地方",
        "那个东西",
        "叫什么",
        "发生过什么",
    ])
    skip_when_latest_user_text_chars_below: int = 4
    skip_when_state_is_sufficient: bool = True


@dataclass
class MemoryConfig:
    enabled: bool = True
    inject_enabled: bool = True
    extraction_enabled: bool = True
    max_recent_turns_for_query: int = 6
    vector_top_k: int = 30
    final_top_k: int = 6
    max_injected_chars: int = 1500
    scopes: ScopesConfig = field(default_factory=ScopesConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    hot_context: HotContextConfig = field(default_factory=HotContextConfig)
    state_updater: StateUpdaterConfig = field(default_factory=StateUpdaterConfig)
    judge: MemoryJudgeConfig = field(default_factory=MemoryJudgeConfig)
    retrieval_gate: RetrievalGateConfig = field(default_factory=RetrievalGateConfig)


@dataclass
class SQLiteConfig:
    app_db: str = "./data/app.sqlite"
    memory_db: str = "./data/memory/memory.sqlite"
    journal_mode: str = "WAL"
    busy_timeout_ms: int = 5000


@dataclass
class LanceDBConfig:
    path: str = "./data/vector_indexes/qwen3_embedding_4096/lancedb"
    table: str = "memories"
    vector_column: str = "vector"
    text_column: str = "content"
    metric: str = "cosine"
    create_fts_index: bool = True


@dataclass
class StorageConfig:
    root_dir: str = "./data"
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)
    lancedb: LanceDBConfig = field(default_factory=LanceDBConfig)


@dataclass
class CompatibilityConfig:
    expose_v1_models: bool = True
    expose_root_chat_completions: bool = True
    cors_enabled: bool = True


@dataclass
class ConversationConfig:
    auto_new_session_gap_minutes: int = 0
    detect_system_prompt_change: bool = False
    detect_message_count_reset: bool = False


@dataclass
class AppConfig:
    language: str = "zh"
    server: ServerConfig = field(default_factory=ServerConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    compatibility: CompatibilityConfig = field(default_factory=CompatibilityConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)


def _merge_dataclass(dc: Any, data: dict) -> Any:
    """Recursively merge dict into a dataclass instance."""
    if not data:
        return dc
    for key, value in data.items():
        if hasattr(dc, key):
            current = getattr(dc, key)
            if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
                _merge_dataclass(current, value)
            else:
                setattr(dc, key, value)
    return dc


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """Load config from YAML file, falling back to defaults."""
    cfg = AppConfig()

    if config_path is None:
        candidates = ["config.yaml", "config.local.yaml", "config.example.yaml"]
        for c in candidates:
            if Path(c).exists():
                config_path = c
                break

    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        _merge_dataclass(cfg, raw)

    return cfg
