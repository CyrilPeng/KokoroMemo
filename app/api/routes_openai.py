"""OpenAI-compatible proxy routes with memory retrieval, injection, and persistence."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.ids import generate_id
from app.core.services import get_embedding_provider, get_lancedb_store
from app.core.state import get_config
from app.memory.card_injector import inject_cards
from app.memory.query_builder import build_retrieval_query
from app.memory.retrieval_gate import RetrievalGateInput, decide_retrieval
from app.memory.state_injector import inject_state_board
from app.memory.state_renderer import render_state_board
from app.memory.state_schema import ConversationStateItem, StateRenderOptions
from app.memory.state_updater import StateUpdaterContext, update_conversation_state
from app.proxy.request_parser import resolve_context, RequestContext
from app.storage.sqlite_app import init_app_db, upsert_conversation
from app.storage.sqlite_cards import init_cards_db
from app.storage.sqlite_conversation import (
    init_chat_db,
    save_raw_request,
    save_raw_response,
    save_injected_memory_log,
    save_turn_and_messages,
    get_turn_count,
)
from app.storage.sqlite_state import SQLiteStateStore, init_state_db

logger = logging.getLogger("kokoromemo.proxy")

router = APIRouter()


@router.get("/v1/models")
async def list_models():
    cfg = get_config()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{cfg.llm.base_url}/models",
                headers={"Authorization": f"Bearer {cfg.llm.get_api_key()}"},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {
        "object": "list",
        "data": [{"id": cfg.llm.model, "object": "model", "created": 0, "owned_by": "kokoromemo"}],
    }


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(request: Request):
    cfg = get_config()
    raw_body: dict[str, Any] = await request.json()
    raw_body_for_persist = deepcopy(raw_body)
    ctx = await resolve_context(request, raw_body, cfg.storage.root_dir)

    await _persist_request(cfg, ctx, raw_body_for_persist)

    # Memory retrieval and injection
    messages = deepcopy(raw_body.get("messages", []))
    injected_messages = messages

    # Resolve template variables in user's system prompt before forwarding
    from app.core.variables import resolve_variables
    var_kwargs = dict(
        username=ctx.user_id,
        character_name=ctx.character_id,
        model_name=cfg.llm.model,
        conversation_id=ctx.conversation_id,
    )
    for i, msg in enumerate(messages):
        if msg.get("role") == "system" and "{{" in msg.get("content", ""):
            messages[i] = dict(msg)
            messages[i]["content"] = resolve_variables(msg["content"], **var_kwargs)

    state_items: list[ConversationStateItem] = []
    state_store: SQLiteStateStore | None = None
    if cfg.memory.enabled and cfg.memory.hot_context.enabled:
        try:
            state_store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
            state_items = await state_store.list_active_items(ctx.conversation_id)
            state_text = render_state_board(
                state_items,
                StateRenderOptions(
                    max_chars=cfg.memory.hot_context.max_chars,
                    include_sections=cfg.memory.hot_context.include_sections,
                    section_order=cfg.memory.hot_context.section_order,
                    max_items_per_section=cfg.memory.hot_context.max_items_per_section,
                ),
            )
            if state_text:
                injected_messages = inject_state_board(injected_messages, state_text)
                await state_store.mark_items_injected([item.item_id for item in state_items if item.item_id])
        except Exception as e:
            logger.warning("Hot context injection failed (degraded): %s", e)

    if cfg.memory.enabled and cfg.memory.inject_enabled and cfg.embedding.enabled:
        try:
            query = build_retrieval_query(
                messages, ctx.user_id, ctx.character_id, ctx.conversation_id,
                max_recent_turns=cfg.memory.max_recent_turns_for_query,
            )
            should_retrieve = True
            if cfg.memory.retrieval_gate.enabled:
                turn_index = await get_turn_count(ctx.chat_db_path, ctx.conversation_id)
                decision = decide_retrieval(
                    RetrievalGateInput(
                        query=query,
                        state_items=state_items,
                        turn_index=turn_index,
                        mode=cfg.memory.retrieval_gate.mode,
                        vector_search_on_new_session=cfg.memory.retrieval_gate.vector_search_on_new_session,
                        vector_search_every_n_turns=cfg.memory.retrieval_gate.vector_search_every_n_turns,
                        vector_search_when_state_confidence_below=cfg.memory.retrieval_gate.vector_search_when_state_confidence_below,
                        trigger_keywords=cfg.memory.retrieval_gate.trigger_keywords,
                        skip_when_latest_user_text_chars_below=cfg.memory.retrieval_gate.skip_when_latest_user_text_chars_below,
                        skip_when_state_is_sufficient=cfg.memory.retrieval_gate.skip_when_state_is_sufficient,
                    )
                )
                should_retrieve = decision.should_retrieve
                try:
                    if state_store is None:
                        state_store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
                    await state_store.record_retrieval_decision(
                        request_id=ctx.request_id,
                        conversation_id=ctx.conversation_id,
                        user_id=ctx.user_id,
                        character_id=ctx.character_id,
                        mode=decision.mode,
                        should_retrieve=decision.should_retrieve,
                        reason=decision.reason,
                        reasons=decision.reasons,
                        latest_user_text=query.latest_user_text,
                        state_item_count=decision.state_item_count,
                        avg_state_confidence=decision.avg_state_confidence,
                        turn_index=turn_index,
                    )
                except Exception as e:
                    logger.warning("Failed to persist retrieval gate decision: %s", e)

            if should_retrieve:
                ep = get_embedding_provider(cfg)
                store = get_lancedb_store(cfg)
                if ep and store:
                    from app.memory.card_retriever import retrieve_cards
                    candidates = await retrieve_cards(
                        query, ep, store,
                        cards_db_path=cfg.storage.sqlite.memory_db,
                        vector_top_k=cfg.memory.vector_top_k,
                        final_top_k=cfg.memory.final_top_k,
                    )
                    if candidates:
                        injected_messages = inject_cards(
                            injected_messages, candidates,
                            max_chars=cfg.memory.max_injected_chars,
                            max_count=cfg.memory.final_top_k,
                            username=ctx.user_id,
                            character_name=ctx.character_id,
                            model_name=cfg.llm.model,
                            conversation_id=ctx.conversation_id,
                        )
                        await _persist_injection(ctx, injected_messages, candidates)
                        logger.info("Injected %d memories for conv=%s", len(candidates), ctx.conversation_id)
        except Exception as e:
            logger.warning("Memory retrieval failed (degraded): %s", e)

    # Build forwarding body with injected messages
    forward_body = deepcopy(raw_body)
    forward_body["messages"] = injected_messages

    is_stream = raw_body.get("stream", False)

    # Determine LLM target based on forward_mode setting
    from app.proxy.llm_providers import create_llm_provider

    # Extract client's auth and model from the incoming request
    client_auth = request.headers.get("authorization", "")
    client_api_key = client_auth.replace("Bearer ", "").strip() if client_auth.startswith("Bearer ") else ""
    client_model = raw_body.get("model", "")

    if cfg.llm.forward_mode == "passthrough":
        # Passthrough: use client's Key and Model, only base_url from config
        final_api_key = client_api_key or cfg.llm.get_api_key()
        final_model = client_model or cfg.llm.model
    else:
        # Override (default): use local config, ignore client values
        final_api_key = cfg.llm.get_api_key()
        final_model = cfg.llm.model or client_model

    final_base_url = cfg.llm.base_url

    # If no base_url configured locally, cannot forward
    if not final_base_url:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={
            "error": {"message": "未配置 LLM Base URL，请在设置中配置对话大模型", "type": "config_error", "param": None, "code": "no_base_url"}
        })

    # Set the model in forward body to the resolved value
    if final_model:
        forward_body["model"] = final_model

    provider = create_llm_provider(
        provider=cfg.llm.provider,
        base_url=final_base_url,
        api_key=final_api_key,
        model=final_model,
    )

    if is_stream:
        return StreamingResponse(
            _stream_proxy(provider, forward_body, cfg.llm.timeout_seconds, ctx, cfg, messages),
            media_type="text/event-stream",
        )
    else:
        return await _non_stream_proxy(provider, forward_body, cfg.llm.timeout_seconds, ctx, cfg, messages)


async def _persist_injection(ctx: RequestContext, injected_messages: list[dict], candidates: list[Any]) -> None:
    injected_text = ""
    for msg in injected_messages:
        content = msg.get("content", "")
        if msg.get("role") == "system" and content.startswith("【KokoroMemo 长期记忆】"):
            injected_text = content
            break

    if not injected_text:
        return

    try:
        card_ids = [getattr(candidate, "card_id", "") for candidate in candidates]
        await save_injected_memory_log(
            ctx.chat_db_path,
            generate_id("inj_"),
            ctx.request_id,
            ctx.conversation_id,
            injected_text,
            json.dumps([card_id for card_id in card_ids if card_id], ensure_ascii=False),
        )
    except Exception as e:
        logger.warning("Failed to persist injection log: %s", e)


async def _persist_request(cfg, ctx: RequestContext, raw_body: dict) -> None:
    try:
        await init_app_db(cfg.storage.sqlite.app_db)
        await init_chat_db(ctx.chat_db_path)
        await init_cards_db(cfg.storage.sqlite.memory_db)
        await init_state_db(cfg.storage.sqlite.memory_db)
        await upsert_conversation(
            cfg.storage.sqlite.app_db, ctx.conversation_id,
            ctx.user_id, ctx.character_id, ctx.client_name, ctx.conv_dir,
        )
        await save_raw_request(
            ctx.chat_db_path, ctx.request_id, ctx.conversation_id,
            json.dumps(raw_body, ensure_ascii=False),
        )
    except Exception as e:
        logger.warning("Failed to persist request: %s", e)


async def _persist_and_extract(ctx: RequestContext, cfg, original_messages: list[dict], assistant_text: str, response_json: str | None, stream_text: str | None) -> None:
    """Save response and extract memories."""
    try:
        resp_id = generate_id("resp_")
        await save_raw_response(
            ctx.chat_db_path, resp_id, ctx.request_id, ctx.conversation_id,
            body_json=response_json, stream_text=stream_text,
        )
        # Save all messages as a turn
        all_msgs = list(original_messages)
        if assistant_text:
            all_msgs.append({"role": "assistant", "content": assistant_text})
        turn_id = generate_id("turn_")
        turn_index = await get_turn_count(ctx.chat_db_path, ctx.conversation_id)
        await save_turn_and_messages(
            ctx.chat_db_path, turn_id, ctx.conversation_id,
            ctx.user_id, ctx.character_id, ctx.request_id, turn_index, all_msgs,
        )
    except Exception as e:
        logger.warning("Failed to persist response: %s", e)
        turn_id = None

    if cfg.memory.enabled and cfg.memory.state_updater.enabled and cfg.memory.state_updater.update_after_each_turn:
        if assistant_text and _should_run_state_updater(cfg, turn_index if 'turn_index' in locals() else None):
            user_msg = _latest_user_message(original_messages)
            if user_msg:
                try:
                    await update_conversation_state(
                        StateUpdaterContext(
                            db_path=cfg.storage.sqlite.memory_db,
                            user_id=ctx.user_id,
                            character_id=ctx.character_id,
                            conversation_id=ctx.conversation_id,
                            turn_id=turn_id if 'turn_id' in locals() else None,
                            mode=cfg.memory.state_updater.mode,
                            min_confidence=cfg.memory.state_updater.min_confidence,
                            llm_provider=cfg.llm.provider,
                            llm_base_url=cfg.llm.base_url,
                            llm_api_key=cfg.llm.get_api_key(),
                            llm_model=cfg.llm.model,
                            llm_timeout_seconds=cfg.llm.timeout_seconds,
                        ),
                        user_msg,
                        assistant_text,
                    )
                except Exception as e:
                    logger.warning("State updater failed: %s", e)

    # Memory extraction via card system
    if not cfg.memory.enabled or not cfg.memory.extraction_enabled:
        return
    if not assistant_text:
        return

    # Ensure cards DB is initialized (may race with _persist_request)
    await init_cards_db(cfg.storage.sqlite.memory_db)

    user_msg = _latest_user_message(original_messages)

    if not user_msg:
        return

    try:
        from app.memory.card_extractor import extract_and_route
        from app.memory.judge import MemoryJudgeConfigView
        ep = get_embedding_provider(cfg)
        store = get_lancedb_store(cfg)
        judge_config = None
        if cfg.memory.judge.enabled:
            judge_config = MemoryJudgeConfigView(
                provider=cfg.memory.judge.provider,
                base_url=cfg.memory.judge.base_url or cfg.llm.base_url,
                api_key=cfg.memory.judge.get_api_key() or cfg.llm.get_api_key(),
                model=cfg.memory.judge.model or cfg.llm.model,
                timeout_seconds=cfg.memory.judge.timeout_seconds,
                temperature=cfg.memory.judge.temperature,
                mode=cfg.memory.judge.mode,
                user_rules=cfg.memory.judge.user_rules,
                prompt=cfg.memory.judge.prompt,
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
            judge_config=judge_config,
        )
    except Exception as e:
        logger.warning("Memory extraction failed: %s", e)


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


async def _non_stream_proxy(provider, body: dict, timeout: int, ctx: RequestContext, cfg, original_messages: list[dict]) -> JSONResponse:
    try:
        resp_data = await provider.chat(body, timeout)

        assistant_text = ""
        choices = resp_data.get("choices", [])
        if choices:
            assistant_text = choices[0].get("message", {}).get("content", "")

        import asyncio
        asyncio.get_event_loop().create_task(
            _persist_and_extract(ctx, cfg, original_messages, assistant_text, json.dumps(resp_data, ensure_ascii=False), None)
        )

        return JSONResponse(content=resp_data, status_code=200)
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": {"message": "Upstream LLM request timed out", "type": "proxy_error", "param": None, "code": "upstream_timeout"}})
    except Exception as e:
        logger.error("Upstream request failed: %s", e)
        return JSONResponse(status_code=502, content={"error": {"message": f"Upstream LLM request failed: {e}", "type": "proxy_error", "param": None, "code": "upstream_error"}})


async def _stream_proxy(provider, body: dict, timeout: int, ctx: RequestContext, cfg, original_messages: list[dict]):
    collected_text: list[str] = []
    try:
        async for line in provider.stream_chat(body, timeout):
            yield f"{line}\n\n"
            if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                try:
                    chunk = json.loads(line[6:])
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        collected_text.append(content)
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass
    except httpx.TimeoutException:
        yield 'data: {"error":{"message":"Upstream LLM stream timed out","type":"proxy_error","code":"upstream_timeout"}}\n\n'
        return
    except Exception as e:
        logger.error("Stream proxy error: %s", e)
        yield f'data: {{"error":{{"message":"Stream error: {e}","type":"proxy_error","code":"upstream_error"}}}}\n\n'
        return

    full_text = "".join(collected_text)
    import asyncio
    asyncio.get_event_loop().create_task(
        _persist_and_extract(ctx, cfg, original_messages, full_text, None, full_text)
    )
