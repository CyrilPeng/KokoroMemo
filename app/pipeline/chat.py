"""Chat completion request pipeline for the OpenAI-compatible proxy."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.degradation import record_degradation
from app.core.ids import generate_id
from app.core.services import ServiceRegistry, get_service_registry
from app.core.state import get_config
from app.memory.card_injector import inject_cards
from app.memory.conversation_policy import get_retrieval_profile
from app.memory.query_builder import build_retrieval_query
from app.memory.retrieval_gate import RetrievalGateInput, decide_retrieval
from app.memory.state_injector import inject_state_board
from app.memory.state_schema import StateRenderOptions
from app.memory.state_table_renderer import render_state_tables
from app.pipeline.postprocess import _persist_response_turn, _schedule_post_process_turn
from app.proxy.request_parser import RequestContext, resolve_context
from app.storage.sqlite_app import upsert_character, upsert_conversation
from app.storage.sqlite_conversation import (
    get_turn_count,
    init_chat_db,
    save_injected_memory_log,
    save_raw_request,
)
from app.storage.sqlite_state import SQLiteStateStore

logger = logging.getLogger("kokoromemo.pipeline.chat")


def _extra_trigger_keywords(cfg) -> list[str]:
    """Return additional trigger keywords for languages other than the config default."""
    from app.core.prompts import TRIGGER_KEYWORDS

    lang = cfg.language
    extra = []
    for key, words in TRIGGER_KEYWORDS.items():
        if key != lang:
            extra.extend(words)
    return extra


@dataclass
class ChatPipelineContext:
    request: Request
    cfg: Any
    ctx: RequestContext
    raw_body: dict[str, Any]
    messages: list[dict]
    injected_messages: list[dict]
    state_store: SQLiteStateStore | None
    conversation_config: Any | None
    should_inject_state: bool
    should_inject_memory: bool
    state_row_count: int = 0
    avg_state_confidence: float | None = None


class ChatPipeline:
    """Coordinates request persistence, memory injection, forwarding and post-processing."""

    def __init__(self, services: ServiceRegistry | None = None) -> None:
        self.services = services or get_service_registry()

    async def handle(self, request: Request, raw_body: dict[str, Any] | None = None):
        prepared = await self.prepare(request, raw_body=raw_body)
        await self.inject_state(prepared)
        await self.inject_memory(prepared)
        return await self.forward(prepared)

    async def prepare(self, request: Request, raw_body: dict[str, Any] | None = None) -> ChatPipelineContext:
        cfg = get_config()
        if raw_body is None:
            raw_body = await request.json()
        ctx = await resolve_context(request, raw_body, cfg.storage.root_dir, cfg)
        await _persist_request(cfg, ctx, deepcopy(raw_body))

        messages = deepcopy(raw_body.get("messages", []))
        self._resolve_system_variables(cfg, ctx, messages)

        state_store = None
        conversation_config = None
        if cfg.memory.enabled:
            try:
                state_store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
                conversation_config = await state_store.ensure_conversation_config(ctx.conversation_id)
            except Exception as exc:
                logger.warning("Conversation policy loading failed (degraded): %s", exc)

        injection_policy = conversation_config.injection_policy if conversation_config else "mixed"
        return ChatPipelineContext(
            request=request,
            cfg=cfg,
            ctx=ctx,
            raw_body=raw_body,
            messages=messages,
            injected_messages=messages,
            state_store=state_store,
            conversation_config=conversation_config,
            should_inject_state=injection_policy in {"state_only", "state_first", "mixed"},
            should_inject_memory=injection_policy in {"memory_only", "state_first", "mixed"},
        )

    async def inject_state(self, prepared: ChatPipelineContext) -> None:
        cfg = prepared.cfg
        if not (cfg.memory.enabled and cfg.memory.hot_context.enabled and prepared.should_inject_state):
            return
        try:
            state_store = prepared.state_store or SQLiteStateStore(cfg.storage.sqlite.memory_db)
            prepared.state_store = state_store
            ctx = prepared.ctx
            table_template = await state_store.get_conversation_table_template(ctx.conversation_id)
            table_rows = await state_store.list_table_rows(
                ctx.conversation_id,
                table_template.template_id if table_template else None,
            )
            active_rows = [row for row in table_rows if row.status == "active"]
            prepared.state_row_count = len(active_rows)
            if active_rows:
                prepared.avg_state_confidence = sum(row.confidence for row in active_rows) / len(active_rows)

            render_options = StateRenderOptions(max_chars=cfg.memory.hot_context.max_chars)
            state_text = render_state_tables(table_template, table_rows, render_options, lang=cfg.language)
            if state_text:
                prepared.injected_messages = inject_state_board(prepared.injected_messages, state_text)
        except Exception as exc:
            record_degradation("state.inject", exc, conversation_id=prepared.ctx.conversation_id)
            logger.warning("Hot context injection failed (degraded): %s", exc)

    async def inject_memory(self, prepared: ChatPipelineContext) -> None:
        cfg = prepared.cfg
        if not (
            cfg.memory.enabled and cfg.memory.inject_enabled and cfg.embedding.enabled and prepared.should_inject_memory
        ):
            return
        try:
            ctx = prepared.ctx
            query = build_retrieval_query(
                prepared.messages,
                ctx.user_id,
                ctx.character_id,
                ctx.conversation_id,
                max_recent_turns=cfg.memory.max_recent_turns_for_query,
            )
            retrieval_profile = get_retrieval_profile(
                prepared.conversation_config.retrieval_profile_id if prepared.conversation_config else None,
                cfg.memory,
            )
            should_retrieve = True
            if cfg.memory.retrieval_gate.enabled:
                turn_index = await get_turn_count(ctx.chat_db_path, ctx.conversation_id)
                decision = decide_retrieval(
                    RetrievalGateInput(
                        query=query,
                        state_row_count=prepared.state_row_count,
                        avg_state_confidence=prepared.avg_state_confidence,
                        turn_index=turn_index,
                        mode=retrieval_profile.gate_mode or cfg.memory.retrieval_gate.mode,
                        vector_search_on_new_session=cfg.memory.retrieval_gate.vector_search_on_new_session,
                        vector_search_every_n_turns=retrieval_profile.vector_search_every_n_turns,
                        vector_search_when_state_confidence_below=cfg.memory.retrieval_gate.vector_search_when_state_confidence_below,
                        trigger_keywords=cfg.memory.retrieval_gate.trigger_keywords + _extra_trigger_keywords(cfg),
                        skip_when_latest_user_text_chars_below=cfg.memory.retrieval_gate.skip_when_latest_user_text_chars_below,
                        skip_when_state_is_sufficient=retrieval_profile.skip_when_state_is_sufficient,
                    )
                )
                should_retrieve = decision.should_retrieve
                decision_id = await self._record_retrieval_decision(prepared, query, decision, turn_index)
            else:
                decision = None
                decision_id = None

            allowed_scopes = {
                scope
                for scope, enabled in (
                    ("global", cfg.memory.scopes.include_global),
                    ("character", cfg.memory.scopes.include_character),
                    ("conversation", cfg.memory.scopes.include_conversation),
                )
                if enabled
            }
            mounted_library_ids = await self._get_mounted_library_ids(prepared)

            if not should_retrieve:
                await self._record_retrieval_trace(
                    prepared,
                    query,
                    should_retrieve=False,
                    trigger_reason=decision.reason if decision else "retrieval_gate_disabled",
                    gate_decision_id=decision_id,
                    retrieval_profile=retrieval_profile.to_dict(),
                    mounted_library_ids=mounted_library_ids,
                    allowed_scopes=allowed_scopes,
                    candidates=[],
                )
                return

            ep = self.services.get_embedding_provider(cfg)
            store = self.services.get_lancedb_store(cfg)
            reranker = self.services.get_rerank_provider(cfg)
            if not ep or not store:
                return

            from app.memory.card_retriever import retrieve_cards

            candidates = await retrieve_cards(
                query,
                ep,
                store,
                cards_db_path=cfg.storage.sqlite.memory_db,
                vector_top_k=retrieval_profile.vector_top_k,
                final_top_k=retrieval_profile.final_top_k,
                scoring_weights={
                    "vector_weight": cfg.memory.scoring.vector_weight,
                    "importance_weight": cfg.memory.scoring.importance_weight,
                    "recency_weight": cfg.memory.scoring.recency_weight,
                    "scope_weight": cfg.memory.scoring.scope_weight,
                    "confidence_weight": cfg.memory.scoring.confidence_weight,
                },
                allowed_scopes=allowed_scopes,
                rerank_provider=reranker,
                rerank_top_k=cfg.rerank.candidate_top_k,
                rerank_batch_size=cfg.rerank.max_documents_per_request,
            )
            await self._record_retrieval_trace(
                prepared,
                query,
                should_retrieve=True,
                trigger_reason=decision.reason if decision else "retrieval_gate_disabled",
                gate_decision_id=decision_id,
                retrieval_profile=retrieval_profile.to_dict(),
                mounted_library_ids=mounted_library_ids,
                allowed_scopes=allowed_scopes,
                candidates=candidates,
            )
            if candidates:
                prepared.injected_messages = inject_cards(
                    prepared.injected_messages,
                    candidates,
                    max_chars=retrieval_profile.max_injected_chars,
                    max_count=retrieval_profile.final_top_k,
                    username=ctx.user_id,
                    character_name=ctx.character_id,
                    model_name=cfg.llm.model,
                    conversation_id=ctx.conversation_id,
                )
                await _persist_injection(ctx, prepared.injected_messages, candidates)
                logger.info("Injected %d memories for conv=%s", len(candidates), ctx.conversation_id)
        except Exception as exc:
            record_degradation("memory.retrieval", exc, conversation_id=prepared.ctx.conversation_id)
            logger.warning("Memory retrieval failed (degraded): %s", exc)

    async def forward(self, prepared: ChatPipelineContext):
        cfg = prepared.cfg
        raw_body = prepared.raw_body
        request = prepared.request
        forward_body = deepcopy(raw_body)
        forward_body["messages"] = prepared.injected_messages

        from app.proxy.llm_providers import create_llm_provider

        client_auth = request.headers.get("authorization", "")
        client_api_key = client_auth.replace("Bearer ", "").strip() if client_auth.startswith("Bearer ") else ""
        client_model = raw_body.get("model", "")
        if cfg.llm.forward_mode == "passthrough":
            final_api_key = client_api_key or cfg.llm.get_api_key()
            final_model = client_model or cfg.llm.model
        else:
            final_api_key = cfg.llm.get_api_key()
            final_model = cfg.llm.model or client_model

        if not cfg.llm.base_url:
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": "未配置 LLM Base URL，请在设置中配置对话大模型",
                        "type": "config_error",
                        "param": None,
                        "code": "no_base_url",
                    }
                },
            )
        if final_model:
            forward_body["model"] = final_model

        provider = create_llm_provider(
            provider=cfg.llm.provider,
            base_url=cfg.llm.base_url,
            api_key=final_api_key,
            model=final_model,
        )
        if raw_body.get("stream", False):
            return StreamingResponse(
                _stream_proxy(
                    provider, forward_body, cfg.llm.timeout_seconds, prepared.ctx, cfg, prepared.messages, self.services
                ),
                media_type="text/event-stream",
            )
        return await _non_stream_proxy(
            provider, forward_body, cfg.llm.timeout_seconds, prepared.ctx, cfg, prepared.messages, self.services
        )

    async def _record_retrieval_decision(
        self, prepared: ChatPipelineContext, query, decision, turn_index: int
    ) -> str | None:
        try:
            cfg = prepared.cfg
            ctx = prepared.ctx
            state_store = prepared.state_store or SQLiteStateStore(cfg.storage.sqlite.memory_db)
            prepared.state_store = state_store
            return await state_store.record_retrieval_decision(
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
        except Exception as exc:
            record_degradation("retrieval.decision", exc, conversation_id=prepared.ctx.conversation_id)
            logger.warning("Failed to persist retrieval gate decision: %s", exc)
            return None

    async def _get_mounted_library_ids(self, prepared: ChatPipelineContext) -> list[str]:
        try:
            from app.storage.sqlite_cards import get_mounted_library_ids

            return await get_mounted_library_ids(prepared.cfg.storage.sqlite.memory_db, prepared.ctx.conversation_id)
        except Exception as exc:
            record_degradation("retrieval.mounts", exc, conversation_id=prepared.ctx.conversation_id)
            logger.warning("Failed to load mounted libraries for retrieval trace: %s", exc)
            return []

    async def _record_retrieval_trace(
        self,
        prepared: ChatPipelineContext,
        query,
        *,
        should_retrieve: bool,
        trigger_reason: str | None,
        gate_decision_id: str | None,
        retrieval_profile: dict | None,
        mounted_library_ids: list[str],
        allowed_scopes: set[str],
        candidates: list[Any],
    ) -> None:
        try:
            cfg = prepared.cfg
            ctx = prepared.ctx
            state_store = prepared.state_store or SQLiteStateStore(cfg.storage.sqlite.memory_db)
            prepared.state_store = state_store
            await state_store.record_retrieval_trace(
                request_id=ctx.request_id,
                gate_decision_id=gate_decision_id,
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id,
                character_id=ctx.character_id,
                query_text=query.query_text,
                should_retrieve=should_retrieve,
                trigger_reason=trigger_reason,
                retrieval_profile_id=(retrieval_profile or {}).get("profile_id"),
                retrieval_profile=retrieval_profile,
                mounted_library_ids=mounted_library_ids,
                allowed_scopes=sorted(allowed_scopes),
                candidates=[_candidate_to_trace_item(candidate) for candidate in candidates],
            )
        except Exception as exc:
            record_degradation("retrieval.trace", exc, conversation_id=prepared.ctx.conversation_id)
            logger.warning("Failed to persist retrieval trace: %s", exc)

    def _resolve_system_variables(self, cfg, ctx: RequestContext, messages: list[dict]) -> None:
        from app.core.variables import resolve_variables

        var_kwargs = dict(
            username=ctx.user_id,
            character_name=ctx.character_id,
            model_name=cfg.llm.model,
            conversation_id=ctx.conversation_id,
        )
        for index, message in enumerate(messages):
            if message.get("role") == "system" and "{{" in message.get("content", ""):
                messages[index] = dict(message)
                messages[index]["content"] = resolve_variables(message["content"], **var_kwargs)


def _candidate_to_trace_item(candidate: Any) -> dict[str, Any]:
    content = getattr(candidate, "content", "") or ""
    return {
        "card_id": getattr(candidate, "card_id", None),
        "library_id": getattr(candidate, "library_id", None),
        "source_conversation_id": getattr(candidate, "source_conversation_id", None),
        "source_character_id": getattr(candidate, "source_character_id", None),
        "route": getattr(candidate, "source", None),
        "vector_score": getattr(candidate, "vector_score", None),
        "importance_score": getattr(candidate, "importance_score", getattr(candidate, "importance", None)),
        "recency_score": getattr(candidate, "recency_score", None),
        "scope_score": getattr(candidate, "scope_score", None),
        "confidence_score": getattr(candidate, "confidence_score", getattr(candidate, "confidence", None)),
        "final_score": getattr(candidate, "final_score", None),
        "selected": True,
        "filtered_reason": None,
        "injection_reason": "selected_for_injection",
        "content_preview": content[:240],
    }


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
        # Migrations are already applied once at startup in AppLifecycle.start().
        # Calling apply_startup_migrations() here on every request was idempotent
        # but redundant and wasteful.
        await init_chat_db(ctx.chat_db_path)
        await upsert_conversation(
            cfg.storage.sqlite.app_db,
            ctx.conversation_id,
            ctx.user_id,
            ctx.character_id,
            ctx.client_name,
            ctx.conv_dir,
        )
        if ctx.character_id:
            await upsert_character(
                cfg.storage.sqlite.app_db,
                ctx.character_id,
                ctx.user_id,
            )
        await _apply_character_defaults_if_new(cfg, ctx)
        await _apply_default_mount_preset_if_new(cfg, ctx)
        await save_raw_request(
            ctx.chat_db_path,
            ctx.request_id,
            ctx.conversation_id,
            json.dumps(raw_body, ensure_ascii=False),
        )
    except Exception as e:
        record_degradation("request.persist", e, conversation_id=ctx.conversation_id)
        logger.warning("Failed to persist request: %s", e)


async def _apply_character_defaults_if_new(cfg, ctx: RequestContext) -> None:
    """Auto-apply character defaults to a new conversation (no existing mounts)."""
    if not ctx.character_id:
        return
    try:
        from app.services.mount_resolver import MountResolver
        from app.storage.sqlite_app import get_character_defaults
        from app.storage.sqlite_cards import set_conversation_mounts
        from app.storage.sqlite_state import SQLiteStateStore

        resolver = MountResolver(cfg.storage.sqlite.memory_db, cfg.storage.sqlite.app_db)
        if await resolver.conversation_has_custom_mounts(ctx.conversation_id):
            return

        defaults = await get_character_defaults(cfg.storage.sqlite.app_db, ctx.character_id)
        if not defaults or not defaults.get("auto_apply"):
            return

        resolved = await resolver.resolve_character_defaults(ctx.character_id, require_auto_apply=True)
        if not resolved:
            return
        await set_conversation_mounts(
            cfg.storage.sqlite.memory_db,
            ctx.conversation_id,
            resolved.mounted_library_ids,
            resolved.write_library_id,
        )

        store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
        await store.set_conversation_config(
            {
                "conversation_id": ctx.conversation_id,
                "profile_id": defaults.get("profile_id"),
                "table_template_id": defaults.get("table_template_id"),
                "mount_preset_id": defaults.get("mount_preset_id"),
                "memory_write_policy": defaults.get("memory_write_policy"),
                "state_update_policy": defaults.get("state_update_policy"),
                "injection_policy": defaults.get("injection_policy"),
                "created_from_default": True,
            }
        )
    except Exception as e:
        logger.debug("Character defaults auto-apply skipped: %s", e)


async def _apply_default_mount_preset_if_new(cfg, ctx: RequestContext) -> None:
    """Auto-apply the global default mount preset to conversations without custom mounts."""
    try:
        from app.services.mount_resolver import MountResolver
        from app.storage.sqlite_cards import set_conversation_mounts

        resolver = MountResolver(cfg.storage.sqlite.memory_db, cfg.storage.sqlite.app_db)
        if await resolver.conversation_has_custom_mounts(ctx.conversation_id):
            return

        resolved = await resolver.resolve_global_defaults()
        if not resolved:
            return
        await set_conversation_mounts(
            cfg.storage.sqlite.memory_db,
            ctx.conversation_id,
            resolved.mounted_library_ids,
            resolved.write_library_id,
        )
    except Exception as e:
        logger.debug("Default mount preset auto-apply skipped: %s", e)


async def _non_stream_proxy(
    provider,
    body: dict,
    timeout: int,
    ctx: RequestContext,
    cfg,
    original_messages: list[dict],
    services: ServiceRegistry,
) -> JSONResponse:
    try:
        resp_data = await provider.chat(body, timeout)

        assistant_text = ""
        finish_reason = None
        choices = resp_data.get("choices", [])
        if choices:
            assistant_text = choices[0].get("message", {}).get("content", "")
            finish_reason = choices[0].get("finish_reason")

        turn_id, turn_index = await _persist_response_turn(
            ctx,
            original_messages,
            assistant_text,
            json.dumps(resp_data, ensure_ascii=False),
            None,
            finish_reason=finish_reason,
        )
        await _schedule_post_process_turn(
            ctx,
            cfg,
            services,
            original_messages,
            assistant_text,
            turn_id,
            turn_index,
            name=f"post_process_turn:{ctx.request_id}",
            finish_reason=finish_reason,
        )

        return JSONResponse(content=resp_data, status_code=200)
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "message": "Upstream LLM request timed out",
                    "type": "proxy_error",
                    "param": None,
                    "code": "upstream_timeout",
                }
            },
        )
    except Exception as e:
        logger.error("Upstream request failed: %s", e)
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": f"Upstream LLM request failed: {e}",
                    "type": "proxy_error",
                    "param": None,
                    "code": "upstream_error",
                }
            },
        )


async def _stream_proxy(
    provider,
    body: dict,
    timeout: int,
    ctx: RequestContext,
    cfg,
    original_messages: list[dict],
    services: ServiceRegistry,
):
    collected_text: list[str] = []
    finish_reason = None
    try:
        async for line in provider.stream_chat(body, timeout):
            yield f"{line}\n\n"
            if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                try:
                    chunk = json.loads(line[6:])
                    choice = chunk.get("choices", [{}])[0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    content = choice.get("delta", {}).get("content")
                    if content:
                        collected_text.append(content)
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass
    except httpx.TimeoutException:
        yield 'data: {"error":{"message":"Upstream LLM stream timed out","type":"proxy_error","code":"upstream_timeout"}}\n\n'
        return
    except Exception as e:
        logger.error("Stream proxy error: %s", e)
        error_payload = json.dumps(
            {"error": {"message": f"Stream error: {e}", "type": "proxy_error", "code": "upstream_error"}}
        )
        yield f"data: {error_payload}\n\n"
        return

    full_text = "".join(collected_text)
    turn_id, turn_index = await _persist_response_turn(
        ctx,
        original_messages,
        full_text,
        None,
        full_text,
        finish_reason=finish_reason,
    )
    await _schedule_post_process_turn(
        ctx,
        cfg,
        services,
        original_messages,
        full_text,
        turn_id,
        turn_index,
        name=f"post_process_turn_stream:{ctx.request_id}",
        finish_reason=finish_reason,
    )
