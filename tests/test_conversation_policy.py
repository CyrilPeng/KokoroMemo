import pytest
from pathlib import Path
from uuid import uuid4

from app.memory.conversation_policy import get_profile, list_profiles
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

    config = await store.ensure_conversation_config("conv_new")
    assert config.conversation_id == "conv_new"
    assert config.created_from_default is True
    assert config.profile_id == default_config.profile_id
    assert config.table_template_id == default_config.table_template_id


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
