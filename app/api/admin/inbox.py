"""Inbox routes: list, approve, reject, restore, delete, cleanup, batch."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Body, HTTPException, Query, Request

from app.api.admin._helpers import _require_admin

router = APIRouter()


@router.get("/admin/inbox")
async def list_inbox(
    status: str = Query(default="pending"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List memory inbox items. status 支持单值，或逗号分隔（如 'discarded,rejected'）。"""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_inbox_items, get_inbox_items_multi

    cfg = get_config()
    statuses = [s.strip() for s in status.split(",") if s.strip()]
    if len(statuses) > 1:
        items, total = await get_inbox_items_multi(cfg.storage.sqlite.memory_db, statuses=statuses, limit=limit, offset=offset)
    else:
        items, total = await get_inbox_items(cfg.storage.sqlite.memory_db, status=statuses[0] if statuses else "pending", limit=limit, offset=offset)
    return {"items": items, "total": total, "status": status}


@router.post("/admin/inbox/{inbox_id}/approve")
async def approve_inbox_item(inbox_id: str):
    """Approve an inbox item → create approved card + vector sync."""
    import json as json_mod

    from app.core.ids import generate_id
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import (
        get_inbox_item,
        get_write_library_id,
        insert_card,
        insert_card_version,
        insert_review_action,
        transition_inbox_status,
        update_inbox_status,
    )
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    item = await get_inbox_item(db_path, inbox_id)
    if not item:
        return {"status": "error", "message": "Inbox item not found"}
    if item["status"] != "pending":
        return {"status": "error", "message": f"Item already {item['status']}"}
    claimed = await transition_inbox_status(db_path, inbox_id, "pending", "approving")
    if not claimed:
        latest = await get_inbox_item(db_path, inbox_id)
        latest_status = latest["status"] if latest else "missing"
        return {"status": "error", "message": f"Item already {latest_status}"}

    try:
        payload = json_mod.loads(item["payload_json"])

        # 创建已批准卡片
        card_id = generate_id("card_")
        library_id = payload.get("library_id") or await get_write_library_id(db_path, payload.get("conversation_id") or "default")
        await insert_card(
            db_path,
            card_id=card_id,
            library_id=library_id,
            user_id=payload.get("user_id", ""),
            character_id=payload.get("character_id"),
            conversation_id=payload.get("conversation_id"),
            scope=payload.get("scope", "global"),
            card_type=payload.get("card_type", "preference"),
            content=payload.get("content", ""),
            importance=payload.get("importance", 0.5),
            confidence=payload.get("confidence", 0.7),
            status="approved",
            evidence_text=payload.get("evidence_text"),
        )
        await insert_card_version(
            db_path,
            card_id=card_id,
            content=payload.get("content", ""),
            card_type=payload.get("card_type", "preference"),
            summary=payload.get("summary"),
            importance=payload.get("importance", 0.5),
            confidence=payload.get("confidence", 0.7),
        )

        # 向量同步
        warning = None
        ep = get_embedding_provider(cfg)
        store = get_lancedb_store(cfg)
        if ep and store:
            try:
                await sync_card_vector(db_path, card_id, ep, store)
            except Exception as e:
                warning = f"Vector sync failed: {e}"
                await enqueue_card_vector_sync(db_path, card_id, str(e))

        # 将待审核条目标记为已批准
        await update_inbox_status(db_path, inbox_id, "approved")
        await insert_review_action(db_path, action="approve", inbox_id=inbox_id, card_id=card_id)
        result = {"status": "ok", "card_id": card_id}
        if warning:
            result["warning"] = warning
        return result
    except Exception:
        await update_inbox_status(db_path, inbox_id, "pending")
        raise


@router.post("/admin/inbox/{inbox_id}/reject")
async def reject_inbox_item(inbox_id: str, data=Body(default="")):
    """Reject an inbox item (moves it to discarded list)."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_inbox_item, insert_review_action, transition_inbox_status

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    item = await get_inbox_item(db_path, inbox_id)
    if not item:
        return {"status": "error", "message": "Inbox item not found"}
    if item["status"] != "pending":
        return {"status": "error", "message": f"Item already {item['status']}"}
    if isinstance(data, dict):
        note = str(data.get("note") or "")
    elif data is None:
        note = ""
    else:
        note = str(data)

    claimed = await transition_inbox_status(db_path, inbox_id, "pending", "discarded", review_note=note)
    if not claimed:
        latest = await get_inbox_item(db_path, inbox_id)
        latest_status = latest["status"] if latest else "missing"
        return {"status": "error", "message": f"Item already {latest_status}"}
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_inbox SET discard_reason = ? WHERE inbox_id = ?",
            ("user_rejected", inbox_id),
        )
        await db.commit()
    await insert_review_action(db_path, action="reject", inbox_id=inbox_id, note=note)
    discarded_keep_limit = cfg.memory.extraction.discarded_keep_limit
    if discarded_keep_limit > 0:
        from app.storage.sqlite_cards import trim_discarded_inbox
        with contextlib.suppress(Exception):
            await trim_discarded_inbox(db_path, discarded_keep_limit)
    return {"status": "ok"}


@router.post("/admin/inbox/{inbox_id}/restore")
async def restore_inbox_item(inbox_id: str):
    """将已丢弃的候选恢复为待审核状态。"""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_inbox_item, insert_review_action, transition_inbox_status

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    item = await get_inbox_item(db_path, inbox_id)
    if not item:
        return {"status": "error", "message": "Inbox item not found"}
    if item["status"] != "discarded":
        return {"status": "error", "message": f"仅已丢弃条目可恢复（当前状态 {item['status']}）"}
    claimed = await transition_inbox_status(db_path, inbox_id, "discarded", "pending", review_note="restored")
    if not claimed:
        latest = await get_inbox_item(db_path, inbox_id)
        latest_status = latest["status"] if latest else "missing"
        return {"status": "error", "message": f"Item already {latest_status}"}
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_inbox SET discard_reason = NULL WHERE inbox_id = ?",
            (inbox_id,),
        )
        await db.commit()
    await insert_review_action(db_path, action="restore", inbox_id=inbox_id, note="discarded->pending")
    return {"status": "ok"}


@router.delete("/admin/inbox/{inbox_id}")
async def delete_inbox_item(inbox_id: str):
    """彻底删除一条 inbox 条目（仅允许 discarded/rejected/approved）。"""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_inbox_item

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    item = await get_inbox_item(db_path, inbox_id)
    if not item:
        return {"status": "error", "message": "Inbox item not found"}
    if item["status"] == "pending":
        return {"status": "error", "message": "待审核条目请先丢弃后再删除"}
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM memory_inbox WHERE inbox_id = ?", (inbox_id,))
        await db.commit()
    return {"status": "ok"}


@router.post("/admin/inbox/cleanup-discarded")
async def cleanup_discarded_inbox(data: dict = Body(default=None)):
    """按当前 keep_limit（或请求传入）裁剪 discarded 条目。"""
    from app.core.state import get_config
    from app.storage.sqlite_cards import trim_discarded_inbox

    cfg = get_config()
    payload = data if isinstance(data, dict) else {}
    keep_limit = payload.get("keep_limit")
    if keep_limit is None:
        keep_limit = cfg.memory.extraction.discarded_keep_limit
    try:
        keep_limit = int(keep_limit)
    except (TypeError, ValueError):
        return {"status": "error", "message": "keep_limit 必须为整数"}
    if keep_limit < 0:
        return {"status": "error", "message": "keep_limit 不能为负数"}
    removed = await trim_discarded_inbox(cfg.storage.sqlite.memory_db, keep_limit)
    return {"status": "ok", "removed": removed, "keep_limit": keep_limit}


@router.post("/admin/inbox/batch")
async def batch_inbox_action(request: Request, data: dict = Body(...)):
    """批量批准或拒绝收件箱项。"""
    _require_admin(request)

    action = data.get("action")  # "approve" or "reject"
    inbox_ids = data.get("inbox_ids") or []
    note = data.get("note") or ""

    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")
    if not isinstance(inbox_ids, list) or not inbox_ids:
        raise HTTPException(status_code=400, detail="inbox_ids required")

    ok = 0
    failed = 0
    for iid in inbox_ids:
        try:
            if action == "approve":
                result = await approve_inbox_item(iid)
            else:
                result = await reject_inbox_item(iid, {"note": note})
            if isinstance(result, dict) and result.get("status") == "ok":
                ok += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return {"status": "ok" if failed == 0 else "partial", "ok": ok, "failed": failed, "action": action}
