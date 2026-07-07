"""AIRP-specific continuity contracts for dashboard and release gates."""

from __future__ import annotations

import json
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.admin._helpers import _require_admin
from app.storage.sqlite_cards import DEFAULT_MEMORY_LIBRARY_ID

router = APIRouter()

_ROUTE_LABELS = {
    "pinned": "置顶/边界卡片",
    "vector": "语义召回",
    "recent": "近期重要卡片",
    "graph": "记忆图谱扩展",
}

_REASON_LABELS = {
    "not_approved": "尚未批准，不能进入召回池",
    "library_not_mounted": "所属记忆库未挂载到当前会话",
    "scope_disabled": "当前召回策略关闭了该作用域",
    "character_isolation": "角色级记忆属于其他角色，已被隔离",
    "conversation_isolation": "会话级记忆属于其他会话，已被隔离",
}

_ISOLATION_FLAG_LABELS = {
    "not_approved": "命中的卡片不是已批准状态",
    "library_not_mounted": "命中的卡片来自未挂载记忆库",
    "character_scope_mismatch": "命中了其他角色的角色级记忆",
    "conversation_scope_mismatch": "命中了其他会话的会话级记忆",
}


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, type(default)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _preview(text: str | None, limit: int = 160) -> str:
    text = (text or "").strip()
    return text[:limit]


def _score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


async def _load_conversation(app_db_path: str, conversation_id: str | None) -> dict | None:
    from app.storage.sqlite_app import init_app_db

    await init_app_db(app_db_path)
    async with aiosqlite.connect(app_db_path) as db:
        db.row_factory = aiosqlite.Row
        if conversation_id:
            cursor = await db.execute(
                """SELECT conv.conversation_id, conv.user_id, conv.character_id, conv.client_name,
                          conv.title, conv.status, conv.first_seen_at, conv.last_seen_at,
                          ch.display_name AS character_display_name
                   FROM conversations conv
                   LEFT JOIN characters ch ON conv.character_id = ch.character_id
                   WHERE conv.conversation_id = ?""",
                (conversation_id,),
            )
        else:
            cursor = await db.execute(
                """SELECT conv.conversation_id, conv.user_id, conv.character_id, conv.client_name,
                          conv.title, conv.status, conv.first_seen_at, conv.last_seen_at,
                          ch.display_name AS character_display_name
                   FROM conversations conv
                   LEFT JOIN characters ch ON conv.character_id = ch.character_id
                   WHERE conv.status = 'active'
                   ORDER BY conv.last_seen_at DESC
                   LIMIT 1"""
            )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        if conversation_id:
            return None
        cursor = await db.execute(
            """SELECT conv.conversation_id, conv.user_id, conv.character_id, conv.client_name,
                      conv.title, conv.status, conv.first_seen_at, conv.last_seen_at,
                      ch.display_name AS character_display_name
               FROM conversations conv
               LEFT JOIN characters ch ON conv.character_id = ch.character_id
               ORDER BY conv.last_seen_at DESC
               LIMIT 1"""
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


def _conversation_from_trace(trace: dict | None) -> dict | None:
    if not trace:
        return None
    return {
        "conversation_id": trace.get("conversation_id"),
        "user_id": trace.get("user_id"),
        "character_id": trace.get("character_id"),
        "client_name": None,
        "title": None,
        "status": None,
        "first_seen_at": None,
        "last_seen_at": None,
        "character_display_name": None,
    }


async def _load_trace(memory_db_path: str, conversation_id: str | None, trace_id: str | None) -> dict | None:
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(memory_db_path)
    if trace_id:
        trace = await store.get_retrieval_trace(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail="Retrieval trace not found")
        if conversation_id and trace.get("conversation_id") != conversation_id:
            raise HTTPException(status_code=400, detail="Trace does not belong to the requested conversation")
        return trace
    if not conversation_id:
        return None
    traces, _total = await store.list_retrieval_traces(conversation_id, limit=1, offset=0)
    if not traces:
        return None
    return await store.get_retrieval_trace(traces[0]["trace_id"])


async def _load_active_mount_ids(memory_db_path: str, conversation_id: str | None) -> list[str]:
    if not conversation_id:
        return [DEFAULT_MEMORY_LIBRARY_ID]
    from app.storage.sqlite_cards import init_cards_db

    await init_cards_db(memory_db_path)
    async with aiosqlite.connect(memory_db_path) as db:
        cursor = await db.execute(
            """SELECT library_id FROM conversation_memory_mounts
               WHERE conversation_id = ? AND status = 'active'
               ORDER BY is_write_target DESC, sort_order ASC, created_at ASC""",
            (conversation_id,),
        )
        rows = [row[0] for row in await cursor.fetchall()]
    return rows or [DEFAULT_MEMORY_LIBRARY_ID]


async def _load_memory_cards(memory_db_path: str, user_id: str | None) -> list[dict]:
    if not user_id:
        return []
    from app.storage.sqlite_cards import init_cards_db

    await init_cards_db(memory_db_path)
    async with aiosqlite.connect(memory_db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT card_id, library_id, user_id, character_id, conversation_id, scope, card_type,
                      title, content, summary, importance, confidence, status, is_pinned,
                      created_at, updated_at
               FROM memory_cards
               WHERE user_id = ? AND status != 'deleted'
               ORDER BY CASE WHEN status = 'approved' THEN 0 ELSE 1 END, updated_at DESC, created_at DESC
               LIMIT 500""",
            (user_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


def _allowed_scopes_from_config(cfg) -> list[str]:
    return [
        scope
        for scope, enabled in (
            ("global", cfg.memory.scopes.include_global),
            ("character", cfg.memory.scopes.include_character),
            ("conversation", cfg.memory.scopes.include_conversation),
        )
        if enabled
    ]


def _card_filter_reasons(
    card: dict,
    *,
    mounted_library_ids: set[str],
    allowed_scopes: set[str],
    current_character_id: str | None,
    current_conversation_id: str | None,
) -> list[str]:
    reasons: list[str] = []
    if card.get("status") != "approved":
        reasons.append("not_approved")
    if mounted_library_ids and card.get("library_id") not in mounted_library_ids:
        reasons.append("library_not_mounted")
    scope = card.get("scope")
    if scope not in allowed_scopes:
        reasons.append("scope_disabled")
    if scope == "character" and card.get("character_id") != current_character_id:
        reasons.append("character_isolation")
    if scope == "conversation" and card.get("conversation_id") != current_conversation_id:
        reasons.append("conversation_isolation")
    return reasons


def _candidate_isolation_flags(
    candidate: dict,
    card: dict | None,
    *,
    mounted_library_ids: set[str],
    current_character_id: str | None,
    current_conversation_id: str | None,
) -> list[str]:
    flags: list[str] = []
    if card and card.get("status") != "approved":
        flags.append("not_approved")
    library_id = (card or candidate).get("library_id")
    if mounted_library_ids and library_id not in mounted_library_ids:
        flags.append("library_not_mounted")
    scope = card.get("scope") if card else None
    character_id = (card or candidate).get("character_id") or candidate.get("source_character_id")
    conversation_id = (card or candidate).get("conversation_id") or candidate.get("source_conversation_id")
    if scope == "character" and character_id != current_character_id:
        flags.append("character_scope_mismatch")
    if scope == "conversation" and conversation_id != current_conversation_id:
        flags.append("conversation_scope_mismatch")
    return flags


def _selection_reason(candidate: dict) -> str:
    route = candidate.get("route")
    route_label = _ROUTE_LABELS.get(route, route or "未知路径")
    final_score = _score(candidate.get("final_score"))
    if final_score is None:
        return f"进入本轮注入：{route_label}。"
    return f"进入本轮注入：{route_label}，综合分 {final_score:.3f}。"


def _candidate_view(
    candidate: dict,
    card: dict | None,
    *,
    mounted_library_ids: set[str],
    current_character_id: str | None,
    current_conversation_id: str | None,
) -> dict:
    flags = _candidate_isolation_flags(
        candidate,
        card,
        mounted_library_ids=mounted_library_ids,
        current_character_id=current_character_id,
        current_conversation_id=current_conversation_id,
    )
    return {
        "card_id": candidate.get("card_id"),
        "library_id": (card or candidate).get("library_id"),
        "scope": card.get("scope") if card else None,
        "card_type": card.get("card_type") if card else None,
        "source_character_id": (card or candidate).get("character_id") or candidate.get("source_character_id"),
        "source_conversation_id": (card or candidate).get("conversation_id") or candidate.get("source_conversation_id"),
        "route": candidate.get("route"),
        "route_label": _ROUTE_LABELS.get(candidate.get("route"), candidate.get("route") or "未知路径"),
        "scores": {
            "vector": _score(candidate.get("vector_score")),
            "importance": _score(candidate.get("importance_score")),
            "recency": _score(candidate.get("recency_score")),
            "scope": _score(candidate.get("scope_score")),
            "confidence": _score(candidate.get("confidence_score")),
            "final": _score(candidate.get("final_score")),
        },
        "selected": bool(candidate.get("selected")),
        "reason_key": candidate.get("injection_reason") or "selected_for_injection",
        "reason": _selection_reason(candidate),
        "filtered_reason": candidate.get("filtered_reason"),
        "content_preview": _preview(candidate.get("content_preview") or (card or {}).get("content")),
        "isolation_flags": flags,
        "isolation_messages": [_ISOLATION_FLAG_LABELS.get(flag, flag) for flag in flags],
    }


def _excluded_memory_view(card: dict, reason_keys: list[str]) -> dict:
    return {
        "card_id": card.get("card_id"),
        "library_id": card.get("library_id"),
        "scope": card.get("scope"),
        "card_type": card.get("card_type"),
        "character_id": card.get("character_id"),
        "conversation_id": card.get("conversation_id"),
        "status": card.get("status"),
        "content_preview": _preview(card.get("content")),
        "primary_reason_key": reason_keys[0] if reason_keys else None,
        "reason_keys": reason_keys,
        "reasons": [_REASON_LABELS.get(key, key) for key in reason_keys],
    }


def _trace_view(trace: dict | None) -> dict | None:
    if not trace:
        return None
    allowed_scopes = _json_loads(trace.get("allowed_scopes_json"), [])
    mounted_libraries = _json_loads(trace.get("mounted_library_ids_json"), [])
    retrieval_profile = _json_loads(trace.get("retrieval_profile_json"), {})
    return {
        "trace_id": trace.get("trace_id"),
        "request_id": trace.get("request_id"),
        "conversation_id": trace.get("conversation_id"),
        "query_text": trace.get("query_text"),
        "should_retrieve": bool(trace.get("should_retrieve")),
        "trigger_reason": trace.get("trigger_reason"),
        "retrieval_profile_id": trace.get("retrieval_profile_id"),
        "retrieval_profile": retrieval_profile,
        "mounted_library_ids": mounted_libraries,
        "allowed_scopes": allowed_scopes,
        "final_injected_count": trace.get("final_injected_count") or 0,
        "created_at": trace.get("created_at"),
    }


def _next_actions(conversation: dict | None, trace: dict | None, selected_with_risk: list[dict]) -> list[dict]:
    if not conversation:
        return [
            {
                "key": "connect_airp_client",
                "label": "接入 AIRP 客户端并产生一轮对话",
                "target": "/settings",
            }
        ]
    if not trace:
        return [
            {
                "key": "create_recall_trace",
                "label": "发起一轮需要称呼、偏好、边界或剧情连续性的对话",
                "target": "/state",
            }
        ]
    if selected_with_risk:
        return [
            {
                "key": "review_isolation_risk",
                "label": "检查角色绑定、记忆库挂载和召回策略",
                "target": "/characters",
            }
        ]
    return [
        {
            "key": "explanation_ready",
            "label": "本轮召回解释可用于验收“不忘、不串、不乱记”",
            "target": "/state",
        }
    ]


@router.get("/admin/airp-recall-explanation")
async def get_airp_recall_explanation(
    request: Request,
    conversation_id: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=50),
):
    """Return an AIRP-focused explanation for the latest memory recall and isolation checks."""
    _require_admin(request)
    from app.core.state import get_config

    cfg = get_config()
    memory_db_path = cfg.storage.sqlite.memory_db

    trace = await _load_trace(memory_db_path, conversation_id, trace_id) if trace_id else None
    resolved_conversation_id = conversation_id or (trace or {}).get("conversation_id")
    conversation = await _load_conversation(cfg.storage.sqlite.app_db, resolved_conversation_id)
    if not conversation and trace:
        conversation = _conversation_from_trace(trace)
    if not trace and conversation:
        trace = await _load_trace(memory_db_path, conversation.get("conversation_id"), None)

    current_conversation_id = conversation.get("conversation_id") if conversation else None
    current_character_id = conversation.get("character_id") if conversation else None
    user_id = conversation.get("user_id") if conversation else (trace or {}).get("user_id")

    trace_data = _trace_view(trace)
    mounted_library_ids = (
        trace_data["mounted_library_ids"]
        if trace_data and trace_data.get("mounted_library_ids")
        else await _load_active_mount_ids(memory_db_path, current_conversation_id)
    )
    allowed_scopes = (
        trace_data["allowed_scopes"]
        if trace_data and trace_data.get("allowed_scopes")
        else _allowed_scopes_from_config(cfg)
    )
    mounted_library_set = set(mounted_library_ids)
    allowed_scope_set = set(allowed_scopes)

    cards = await _load_memory_cards(memory_db_path, user_id)
    card_by_id = {card["card_id"]: card for card in cards}
    trace_candidates = (trace or {}).get("candidates") or []
    selected_candidates = [item for item in trace_candidates if item.get("selected")]
    rejected_candidates = [item for item in trace_candidates if not item.get("selected")]
    selected_ids = {item.get("card_id") for item in selected_candidates if item.get("card_id")}

    all_selected_memories = [
        _candidate_view(
            item,
            card_by_id.get(item.get("card_id")),
            mounted_library_ids=mounted_library_set,
            current_character_id=current_character_id,
            current_conversation_id=current_conversation_id,
        )
        for item in selected_candidates
    ]
    all_rejected = [
        _candidate_view(
            item,
            card_by_id.get(item.get("card_id")),
            mounted_library_ids=mounted_library_set,
            current_character_id=current_character_id,
            current_conversation_id=current_conversation_id,
        )
        for item in rejected_candidates
    ]

    all_excluded_memories = []
    for card in cards:
        if card.get("card_id") in selected_ids:
            continue
        reasons = _card_filter_reasons(
            card,
            mounted_library_ids=mounted_library_set,
            allowed_scopes=allowed_scope_set,
            current_character_id=current_character_id,
            current_conversation_id=current_conversation_id,
        )
        if reasons:
            all_excluded_memories.append(_excluded_memory_view(card, reasons))

    selected_with_risk = [item for item in all_selected_memories if item["isolation_flags"]]
    character_isolation_excluded_count = sum(
        1 for item in all_excluded_memories if "character_isolation" in item["reason_keys"]
    )
    conversation_isolation_excluded_count = sum(
        1 for item in all_excluded_memories if "conversation_isolation" in item["reason_keys"]
    )
    library_excluded_count = sum(1 for item in all_excluded_memories if "library_not_mounted" in item["reason_keys"])
    isolation_passed = bool(trace) and not selected_with_risk

    return {
        "status": "ok",
        "ready": bool(conversation and trace and isolation_passed),
        "conversation": conversation,
        "current_role": {
            "character_id": current_character_id,
            "display_name": (conversation or {}).get("character_display_name") or current_character_id,
        },
        "trace": trace_data,
        "selected_memories": all_selected_memories[:limit],
        "rejected_candidates": all_rejected[:limit],
        "excluded_memories": all_excluded_memories[:limit],
        "isolation": {
            "passed": isolation_passed,
            "current_character_id": current_character_id,
            "selected_risk_count": len(selected_with_risk),
            "selected_risks": selected_with_risk,
            "character_isolation_excluded_count": character_isolation_excluded_count,
            "conversation_isolation_excluded_count": conversation_isolation_excluded_count,
            "library_excluded_count": library_excluded_count,
        },
        "summary": {
            "selected_count": len(selected_candidates),
            "rejected_candidate_count": len(rejected_candidates),
            "excluded_memory_count": len(all_excluded_memories),
            "character_isolation_excluded_count": character_isolation_excluded_count,
            "conversation_isolation_excluded_count": conversation_isolation_excluded_count,
            "library_excluded_count": library_excluded_count,
            "mounted_library_ids": mounted_library_ids,
            "allowed_scopes": allowed_scopes,
        },
        "next_actions": _next_actions(conversation, trace, selected_with_risk),
    }
