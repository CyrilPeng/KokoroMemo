"""Post-turn persistence, state update and memory extraction pipeline."""

from __future__ import annotations

import logging

from app.core.background import spawn_background
from app.core.conversation_locks import conversation_lock
from app.core.degradation import record_degradation
from app.core.ids import generate_id
from app.core.services import ServiceRegistry
from app.memory.state_filler import StateFillerConfigView
from app.memory.state_table_filler import fill_conversation_state_tables
from app.proxy.request_parser import RequestContext
from app.storage.sqlite_conversation import get_turn_count, save_raw_response, save_turn_and_messages
from app.storage.sqlite_state import SQLiteStateStore

logger = logging.getLogger("kokoromemo.pipeline.postprocess")


async def _persist_response_turn(
    ctx: RequestContext,
    original_messages: list[dict],
    assistant_text: str,
    response_json: str | None,
    stream_text: str | None,
    *,
    finish_reason: str | None = None,
) -> tuple[str | None, int | None]:
    try:
        resp_id = generate_id("resp_")
        await save_raw_response(
            ctx.chat_db_path,
            resp_id,
            ctx.request_id,
            ctx.conversation_id,
            body_json=response_json,
            stream_text=stream_text,
            finish_reason=finish_reason,
        )
        all_msgs = list(original_messages)
        if assistant_text:
            all_msgs.append({"role": "assistant", "content": assistant_text})
        turn_id = generate_id("turn_")
        turn_index = await get_turn_count(ctx.chat_db_path, ctx.conversation_id)
        await save_turn_and_messages(
            ctx.chat_db_path,
            turn_id,
            ctx.conversation_id,
            ctx.user_id,
            ctx.character_id,
            ctx.request_id,
            turn_index,
            all_msgs,
        )
        return turn_id, turn_index
    except Exception as exc:
        record_degradation("response.persist", exc, conversation_id=ctx.conversation_id)
        logger.warning("Failed to persist response: %s", exc)
        return None, None


async def _schedule_post_process_turn(
    ctx: RequestContext,
    cfg,
    services: ServiceRegistry,
    original_messages: list[dict],
    assistant_text: str,
    turn_id: str | None,
    turn_index: int | None,
    *,
    name: str,
    finish_reason: str | None = None,
) -> None:
    spawn_background(
        _post_process_turn(
            ctx,
            cfg,
            services,
            original_messages,
            assistant_text,
            turn_id,
            turn_index,
            finish_reason=finish_reason,
        ),
        name=name,
    )


async def _post_process_turn(
    ctx: RequestContext,
    cfg,
    services: ServiceRegistry,
    original_messages: list[dict],
    assistant_text: str,
    turn_id: str | None,
    turn_index: int | None,
    *,
    finish_reason: str | None = None,
) -> None:
    async with conversation_lock(ctx.conversation_id):
        await _update_state_and_extract_memories(
            ctx,
            cfg,
            services,
            original_messages,
            assistant_text,
            turn_id,
            turn_index,
            finish_reason=finish_reason,
        )


async def _update_state_and_extract_memories(
    ctx: RequestContext,
    cfg,
    services: ServiceRegistry,
    original_messages: list[dict],
    assistant_text: str,
    turn_id: str | None,
    turn_index: int | None,
    *,
    finish_reason: str | None = None,
) -> None:
    if _is_truncated_finish_reason(finish_reason):
        logger.warning(
            "Skipped state update and memory extraction for conv=%s: assistant response was truncated (finish_reason=%s)",
            ctx.conversation_id,
            finish_reason,
        )
        return

    conversation_config = None
    if cfg.memory.enabled:
        try:
            conversation_config = await SQLiteStateStore(cfg.storage.sqlite.memory_db).ensure_conversation_config(
                ctx.conversation_id
            )
        except Exception as exc:
            record_degradation("conversation.policy", exc, conversation_id=ctx.conversation_id)
            logger.warning("Conversation policy loading failed during extraction (degraded): %s", exc)

    state_update_policy = conversation_config.state_update_policy if conversation_config else "auto"
    memory_write_policy = conversation_config.memory_write_policy if conversation_config else "candidate"

    if (
        cfg.memory.enabled
        and cfg.memory.state_updater.enabled
        and cfg.memory.state_updater.update_after_each_turn
        and state_update_policy == "auto"
        and assistant_text
        and _should_run_state_updater(cfg, turn_index)
    ):
        user_msg = _latest_user_message(original_messages)
        if user_msg:
            try:
                await fill_conversation_state_tables(
                    db_path=cfg.storage.sqlite.memory_db,
                    conversation_id=ctx.conversation_id,
                    user_message=user_msg,
                    assistant_message=assistant_text,
                    turn_id=turn_id,
                    config=StateFillerConfigView(
                        provider=cfg.memory.state_updater.provider,
                        base_url=cfg.memory.state_updater.base_url or cfg.memory.judge.base_url or cfg.llm.base_url,
                        api_key=cfg.memory.state_updater.get_api_key()
                        or cfg.memory.judge.get_api_key()
                        or cfg.llm.get_api_key(),
                        model=cfg.memory.state_updater.model or cfg.memory.judge.model or cfg.llm.model,
                        timeout_seconds=cfg.memory.state_updater.timeout_seconds,
                        temperature=cfg.memory.state_updater.temperature,
                        min_confidence=cfg.memory.state_updater.min_confidence,
                        prompt=cfg.memory.state_updater.prompt,
                    ),
                    lang=cfg.language,
                )
            except Exception as exc:
                record_degradation("state.update", exc, conversation_id=ctx.conversation_id)
                logger.warning("State updater failed: %s", exc)

    if not cfg.memory.enabled or not cfg.memory.extraction_enabled:
        return
    if memory_write_policy == "disabled":
        logger.info("Memory extraction skipped for conv=%s by policy=disabled", ctx.conversation_id)
        return
    if not assistant_text:
        return

    user_msg = _latest_user_message(original_messages)
    if not user_msg:
        return

    try:
        from app.memory.card_extractor import extract_and_route
        from app.memory.judge import MemoryJudgeConfigView

        ep = services.get_embedding_provider(cfg)
        store = services.get_vector_store(cfg)
        judge_config = None
        if cfg.memory.judge.enabled:
            user_rules = cfg.memory.judge.user_rules
            if memory_write_policy == "stable_only":
                user_rules = (
                    f"{user_rules}\n\n"
                    "当前会话策略为 stable_only：只允许用户偏好、角色稳定设定、世界观常识、稳定关系等长期事实进入记忆候选；"
                    "临时事件、机械状态、剧情进度、资源变化、任务进度、小人即时状态等必须判为不写入长期记忆。"
                ).strip()
            judge_config = MemoryJudgeConfigView(
                provider=cfg.memory.judge.provider,
                base_url=cfg.memory.judge.base_url or cfg.llm.base_url,
                api_key=cfg.memory.judge.get_api_key() or cfg.llm.get_api_key(),
                model=cfg.memory.judge.model or cfg.llm.model,
                timeout_seconds=cfg.memory.judge.timeout_seconds,
                temperature=cfg.memory.judge.temperature,
                mode=cfg.memory.judge.mode,
                user_rules=user_rules,
                prompt=cfg.memory.judge.prompt,
                reject_unverified=cfg.memory.judge.reject_unverified,
            )

        await extract_and_route(
            db_path=cfg.storage.sqlite.memory_db,
            user_message=user_msg,
            assistant_message=assistant_text,
            user_id=ctx.user_id,
            character_id=ctx.character_id,
            conversation_id=ctx.conversation_id,
            embedding_provider=ep,
            lancedb_store=store,
            min_importance=cfg.memory.extraction.min_importance,
            min_confidence=cfg.memory.extraction.min_confidence,
            semantic_dedup_threshold=cfg.memory.extraction.semantic_dedup_threshold,
            judge_config=judge_config,
            lang=cfg.language,
            discarded_keep_limit=cfg.memory.extraction.discarded_keep_limit,
        )
    except Exception as exc:
        record_degradation("memory.extraction", exc, conversation_id=ctx.conversation_id)
        logger.warning("Memory extraction failed: %s", exc)


def _latest_user_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _should_run_state_updater(cfg, turn_index: int | None) -> bool:
    every_n = cfg.memory.state_updater.update_every_n_turns
    if every_n <= 1 or turn_index is None:
        return True
    return turn_index % every_n == 0


def _is_truncated_finish_reason(finish_reason: str | None) -> bool:
    return str(finish_reason or "").strip().lower() in {"length", "max_tokens"}
