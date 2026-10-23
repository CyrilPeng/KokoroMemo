from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import MemoryConfig
from app.memory.conversation_policy import (
    get_profile,
    get_retrieval_profile,
    list_profiles,
    list_retrieval_profiles,
)
from app.storage.sqlite_state import SQLiteStateStore


def _db_path() -> str:
    root = Path(__file__).resolve().parent.parent / ".test_dbs"
    root.mkdir(exist_ok=True)
    return str(root / f"conversation_policy_{uuid4().hex}.sqlite")


@pytest.mark.asyncio
async def test_default_conversation_config_creates_new_conversation():
    db_path = _db_path()
    store = SQLiteStateStore(db_path)

    default_config = await store.get_default_conversation_config()
    assert default_config.profile_id == "airp_roleplay"
    assert default_config.injection_policy == "mixed"
    assert default_config.retrieval_profile_id == "balanced"

    config = await store.ensure_conversation_config("conv_new")
    assert config.conversation_id == "conv_new"
    assert config.created_from_default is True
    assert config.profile_id == default_config.profile_id
    assert config.table_template_id == default_config.table_template_id
    assert config.retrieval_profile_id == default_config.retrieval_profile_id


@pytest.mark.asyncio
async def test_updated_defaults_apply_only_to_new_conversations():
    db_path = _db_path()
    store = SQLiteStateStore(db_path)

    old_config = await store.ensure_conversation_config("conv_old")
    rimtalk = get_profile("rimtalk_colony")
    await store.set_default_conversation_config(rimtalk.to_dict())

    new_config = await store.ensure_conversation_config("conv_new")
    unchanged_old = await store.ensure_conversation_config("conv_old")

    assert old_config.profile_id == "airp_roleplay"
    assert unchanged_old.profile_id == "airp_roleplay"
    assert new_config.profile_id == "rimtalk_colony"
    assert new_config.memory_write_policy == "disabled"
    assert new_config.injection_policy == "state_only"


@pytest.mark.asyncio
async def test_profile_table_templates_are_available():
    db_path = _db_path()
    store = SQLiteStateStore(db_path)

    rimtalk = await store.get_table_template("tpl_rimtalk_colony_tables")
    ttrpg = await store.get_table_template("tpl_ttrpg_story_tables")

    assert rimtalk is not None
    assert {table.table_key for table in rimtalk.tables} >= {"colony_overview", "pawn_state", "resources"}
    assert ttrpg is not None
    assert {table.table_key for table in ttrpg.tables} >= {"party", "quests_clues", "story_flags"}


def test_builtin_profiles_cover_required_modes():
    profile_ids = {profile.profile_id for profile in list_profiles()}
    assert {"airp_roleplay", "rimtalk_colony", "ttrpg_story", "memory_only", "proxy_only"} <= profile_ids


def test_builtin_retrieval_profiles_cover_required_modes():
    profiles = {profile.profile_id: profile for profile in list_retrieval_profiles()}
    assert {"conservative", "balanced", "high_recall", "state_first", "memory_first"} <= set(profiles)
    assert profiles["balanced"].final_top_k == 6
    assert profiles["high_recall"].vector_top_k > profiles["balanced"].vector_top_k


def test_balanced_retrieval_profile_uses_global_memory_config():
    memory = MemoryConfig(vector_top_k=12, final_top_k=3, max_injected_chars=777)

    balanced = get_retrieval_profile("balanced", memory)
    assert balanced.vector_top_k == 12
    assert balanced.final_top_k == 3
    assert balanced.max_injected_chars == 777

    high_recall = get_retrieval_profile("high_recall", memory)
    assert high_recall.vector_top_k == 50
    assert high_recall.final_top_k == 10
    assert high_recall.max_injected_chars == 2200


def test_list_retrieval_profiles_applies_global_config_to_balanced_only():
    memory = MemoryConfig(vector_top_k=12, final_top_k=3, max_injected_chars=777)
    profiles = {profile.profile_id: profile for profile in list_retrieval_profiles(memory)}

    assert profiles["balanced"].vector_top_k == 12
    assert profiles["high_recall"].vector_top_k == 50
