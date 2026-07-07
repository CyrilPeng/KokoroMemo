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

_CARD_TYPE_LABELS = {
    "preference": "偏好",
    "boundary": "边界",
    "relationship": "关系",
    "event": "事件",
    "promise": "承诺",
    "correction": "纠正",
    "world_state": "世界状态",
    "summary": "摘要",
}

_SCOPE_LABELS = {
    "global": "全局",
    "character": "角色",
    "conversation": "会话",
}

_DISCARD_REASON_LABELS = {
    "exact_duplicate": "精确重复",
    "semantic_duplicate": "语义近似重复",
    "auto_rejected": "自动审核拒绝",
    "user_rejected": "用户审核拒绝",
    "too_low_confidence": "置信度过低",
    "too_low_importance": "重要性过低",
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


def _payload_json(row: dict) -> dict:
    return _json_loads(row.get("payload_json"), {})


def _type_label(card_type: str | None) -> str:
    return _CARD_TYPE_LABELS.get(card_type or "", card_type or "未分类")


def _scope_label(scope: str | None) -> str:
    return _SCOPE_LABELS.get(scope or "", scope or "未设置")


def _discard_reason_label(reason: str | None) -> str:
    return _DISCARD_REASON_LABELS.get(reason or "", reason or "未记录")


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


def _matches_airp_context(
    row: dict,
    *,
    current_character_id: str | None,
    current_conversation_id: str | None,
    include_global: bool = True,
) -> bool:
    scope = row.get("scope")
    if include_global and scope == "global":
        return True
    if scope == "character":
        return bool(current_character_id) and row.get("character_id") == current_character_id
    if scope == "conversation":
        return bool(current_conversation_id) and row.get("conversation_id") == current_conversation_id
    return bool(current_character_id and row.get("character_id") == current_character_id) or bool(
        current_conversation_id and row.get("conversation_id") == current_conversation_id
    )


def _inbox_matches_airp_context(
    item: dict,
    *,
    current_character_id: str | None,
    current_conversation_id: str | None,
) -> bool:
    payload = _payload_json(item)
    character_id = payload.get("character_id") or item.get("character_id")
    conversation_id = payload.get("conversation_id") or item.get("conversation_id")
    scope = payload.get("scope")
    if scope == "global":
        return True
    return bool(current_character_id and character_id == current_character_id) or bool(
        current_conversation_id and conversation_id == current_conversation_id
    )


async def _load_review_actions(memory_db_path: str, card_ids: list[str]) -> dict[str, list[dict]]:
    if not card_ids:
        return {}
    from app.storage.sqlite_cards import init_cards_db

    await init_cards_db(memory_db_path)
    async with aiosqlite.connect(memory_db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("CREATE TEMP TABLE requested_review_card_ids (card_id TEXT PRIMARY KEY)")
        await db.executemany(
            "INSERT OR IGNORE INTO requested_review_card_ids(card_id) VALUES (?)",
            [(card_id,) for card_id in card_ids],
        )
        cursor = await db.execute(
            """SELECT action_id, inbox_id, review_actions.card_id, action, reviewer, note, created_at
                FROM review_actions
                INNER JOIN requested_review_card_ids
                    ON requested_review_card_ids.card_id = review_actions.card_id
                ORDER BY created_at DESC""",
        )
        actions: dict[str, list[dict]] = {}
        for row in await cursor.fetchall():
            data = dict(row)
            actions.setdefault(data["card_id"], []).append(data)
        return actions


async def _load_memory_audit_rows(memory_db_path: str, user_id: str | None) -> tuple[list[dict], list[dict]]:
    if not user_id:
        return [], []
    from app.storage.sqlite_cards import init_cards_db

    await init_cards_db(memory_db_path)
    async with aiosqlite.connect(memory_db_path) as db:
        db.row_factory = aiosqlite.Row
        cards_cursor = await db.execute(
            """SELECT card_id, library_id, user_id, character_id, conversation_id, scope, card_type,
                      title, content, summary, importance, confidence, status, is_pinned,
                      evidence_text, created_at, updated_at
               FROM memory_cards
               WHERE user_id = ? AND status IN ('approved', 'deprecated')
               ORDER BY CASE WHEN status = 'approved' THEN 0 ELSE 1 END, updated_at DESC, created_at DESC
               LIMIT 500""",
            (user_id,),
        )
        inbox_cursor = await db.execute(
            """SELECT inbox_id, library_id, candidate_type, payload_json, user_id, character_id,
                      conversation_id, suggested_action, risk_level, reason, status, reviewed_at,
                      review_note, created_at, discard_reason, related_card_id
               FROM memory_inbox
               WHERE user_id = ? AND status IN ('pending', 'discarded', 'rejected', 'approved')
               ORDER BY created_at DESC
               LIMIT 500""",
            (user_id,),
        )
        return [dict(row) for row in await cards_cursor.fetchall()], [
            dict(row) for row in await inbox_cursor.fetchall()
        ]


def _remember_reason(card: dict, review_actions: list[dict]) -> str:
    scope = card.get("scope")
    type_label = _type_label(card.get("card_type"))
    if review_actions:
        return f"已通过本地审核进入长期记忆；类型为{type_label}，作用域为{_scope_label(scope)}。"
    if card.get("evidence_text"):
        return f"根据对话证据写入长期记忆；类型为{type_label}，作用域为{_scope_label(scope)}。"
    return f"已批准长期记忆；类型为{type_label}，作用域为{_scope_label(scope)}。"


def _memory_card_view(card: dict, review_actions: list[dict]) -> dict:
    return {
        "card_id": card.get("card_id"),
        "library_id": card.get("library_id"),
        "scope": card.get("scope"),
        "scope_label": _scope_label(card.get("scope")),
        "card_type": card.get("card_type"),
        "card_type_label": _type_label(card.get("card_type")),
        "status": card.get("status"),
        "character_id": card.get("character_id"),
        "conversation_id": card.get("conversation_id"),
        "content_preview": _preview(card.get("content")),
        "summary": card.get("summary"),
        "importance": _score(card.get("importance")),
        "confidence": _score(card.get("confidence")),
        "evidence_preview": _preview(card.get("evidence_text")),
        "remember_reason": _remember_reason(card, review_actions),
        "review_actions": review_actions[:3],
        "created_at": card.get("created_at"),
        "updated_at": card.get("updated_at"),
    }


def _pending_candidate_reason(item: dict, payload: dict) -> str:
    type_label = _type_label(payload.get("card_type") or item.get("candidate_type"))
    risk = item.get("risk_level") or "low"
    if risk == "high":
        return f"候选属于{type_label}，风险较高，需要人工确认后才会写入。"
    if risk == "medium":
        return f"候选属于{type_label}，需要审核确认稳定性。"
    return f"候选属于{type_label}，等待审核进入长期记忆。"


def _rejected_candidate_reason(item: dict, payload: dict) -> str:
    if item.get("review_note"):
        return f"用户审核拒绝：{item['review_note']}"
    if item.get("discard_reason"):
        return _discard_reason_label(item.get("discard_reason"))
    if item.get("reason"):
        return str(item["reason"])
    if payload.get("reason"):
        return str(payload["reason"])
    return "未进入长期记忆。"


def _candidate_view_from_inbox(item: dict) -> dict:
    payload = _payload_json(item)
    content = payload.get("content") or payload.get("summary") or item.get("reason")
    status = item.get("status")
    reason = (
        _pending_candidate_reason(item, payload) if status == "pending" else _rejected_candidate_reason(item, payload)
    )
    return {
        "inbox_id": item.get("inbox_id"),
        "library_id": item.get("library_id") or payload.get("library_id"),
        "status": status,
        "candidate_type": item.get("candidate_type"),
        "card_type": payload.get("card_type") or item.get("candidate_type"),
        "card_type_label": _type_label(payload.get("card_type") or item.get("candidate_type")),
        "scope": payload.get("scope"),
        "scope_label": _scope_label(payload.get("scope")),
        "risk_level": item.get("risk_level"),
        "suggested_action": item.get("suggested_action"),
        "character_id": payload.get("character_id") or item.get("character_id"),
        "conversation_id": payload.get("conversation_id") or item.get("conversation_id"),
        "content_preview": _preview(content),
        "importance": _score(payload.get("importance")),
        "confidence": _score(payload.get("confidence")),
        "reason": reason,
        "source_reason": item.get("reason"),
        "review_note": item.get("review_note"),
        "discard_reason": item.get("discard_reason"),
        "discard_reason_label": _discard_reason_label(item.get("discard_reason")),
        "related_card_id": item.get("related_card_id"),
        "created_at": item.get("created_at"),
        "reviewed_at": item.get("reviewed_at"),
    }


async def _load_state_rows(memory_db_path: str, conversation_id: str | None, limit: int) -> list[dict]:
    if not conversation_id:
        return []
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(memory_db_path)
    template = await store.get_conversation_table_template(conversation_id)
    rows = await store.list_table_rows(conversation_id, template.template_id if template else None)
    table_names = {table.table_key: table.name for table in template.tables} if template else {}
    result = []
    for row in rows:
        if row.status != "active":
            continue
        result.append(
            {
                "row_id": row.row_id,
                "table_key": row.table_key,
                "table_name": table_names.get(row.table_key, row.table_key),
                "status": row.status,
                "confidence": _score(row.confidence),
                "source": row.source,
                "values": {key: cell.value for key, cell in row.cells.items()},
                "updated_at": row.updated_at,
            }
        )
    return result[:limit]


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


@router.get("/admin/airp-memory-audit")
async def get_airp_memory_audit(
    request: Request,
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=6, ge=1, le=50),
):
    """Return an AIRP-facing ledger of remembered, pending, rejected memory and current state."""
    _require_admin(request)
    from app.core.state import get_config

    cfg = get_config()
    conversation = await _load_conversation(cfg.storage.sqlite.app_db, conversation_id)
    current_conversation_id = conversation.get("conversation_id") if conversation else None
    current_character_id = conversation.get("character_id") if conversation else None
    user_id = conversation.get("user_id") if conversation else None

    cards, inbox_items = await _load_memory_audit_rows(cfg.storage.sqlite.memory_db, user_id)
    context_cards = [
        card
        for card in cards
        if _matches_airp_context(
            card,
            current_character_id=current_character_id,
            current_conversation_id=current_conversation_id,
        )
    ]
    review_actions = await _load_review_actions(
        cfg.storage.sqlite.memory_db, [card["card_id"] for card in context_cards]
    )
    remembered = [
        _memory_card_view(card, review_actions.get(card["card_id"], []))
        for card in context_cards
        if card.get("status") == "approved"
    ]
    deprecated = [
        _memory_card_view(card, review_actions.get(card["card_id"], []))
        for card in context_cards
        if card.get("status") == "deprecated"
    ]
    context_inbox = [
        item
        for item in inbox_items
        if _inbox_matches_airp_context(
            item,
            current_character_id=current_character_id,
            current_conversation_id=current_conversation_id,
        )
    ]
    pending = [_candidate_view_from_inbox(item) for item in context_inbox if item.get("status") == "pending"]
    rejected = [
        _candidate_view_from_inbox(item) for item in context_inbox if item.get("status") in {"discarded", "rejected"}
    ]
    approved_candidates = [
        _candidate_view_from_inbox(item) for item in context_inbox if item.get("status") == "approved"
    ]
    state_rows = await _load_state_rows(cfg.storage.sqlite.memory_db, current_conversation_id, limit)

    has_memory_or_state = bool(remembered or pending or rejected or state_rows)
    next_actions = []
    if not conversation:
        next_actions.append(
            {"key": "connect_airp_client", "label": "接入 AIRP 客户端并产生一轮对话", "target": "/settings"}
        )
    if conversation and not remembered and not pending:
        next_actions.append(
            {"key": "create_stable_memory", "label": "让角色听到一条稳定称呼、偏好或边界", "target": "/inbox"}
        )
    if pending:
        next_actions.append({"key": "review_pending_memory", "label": "审核待处理候选记忆", "target": "/inbox"})
    if conversation and not state_rows:
        next_actions.append({"key": "confirm_state_board", "label": "在状态板确认当前剧情状态", "target": "/state"})
    if not next_actions and has_memory_or_state:
        next_actions.append({"key": "audit_ready", "label": "记忆审核账本可用于确认不忘与不乱记", "target": "/inbox"})

    return {
        "status": "ok",
        "ready": bool(conversation and has_memory_or_state),
        "conversation": conversation,
        "current_role": {
            "character_id": current_character_id,
            "display_name": (conversation or {}).get("character_display_name") or current_character_id,
        },
        "remembered_memories": remembered[:limit],
        "pending_candidates": pending[:limit],
        "rejected_memories": rejected[:limit],
        "deprecated_memories": deprecated[:limit],
        "approved_candidates": approved_candidates[:limit],
        "current_state": {
            "conversation_id": current_conversation_id,
            "row_count": len(state_rows),
            "rows": state_rows,
            "target": "/state",
        },
        "summary": {
            "remembered_count": len(remembered),
            "pending_candidate_count": len(pending),
            "rejected_memory_count": len(rejected),
            "deprecated_memory_count": len(deprecated),
            "approved_candidate_count": len(approved_candidates),
            "state_row_count": len(state_rows),
        },
        "next_actions": next_actions,
    }
