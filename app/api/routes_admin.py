"""Health check and admin routes."""

from __future__ import annotations

from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Query, Body, Request, HTTPException

router = APIRouter()


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


@router.get("/admin/conversation-profiles")
async def list_conversation_profiles_api(request: Request):
    """List built-in conversation policy profiles."""
    _require_admin(request)
    from app.memory.conversation_policy import list_profiles

    return {"items": [profile.to_dict() for profile in list_profiles()]}


@router.get("/admin/conversation-defaults")
async def get_conversation_defaults_api(request: Request):
    """Get default policy for newly seen conversations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    return await store.get_default_conversation_config()


@router.put("/admin/conversation-defaults")
async def update_conversation_defaults_api(request: Request, data: dict = Body(...)):
    """Update default policy for newly seen conversations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    config = await store.set_default_conversation_config(data)
    return {"status": "ok", "config": config.to_dict()}


@router.get("/admin/conversations/{conversation_id}/config")
async def get_conversation_config_api(conversation_id: str, request: Request):
    """Get conversation policy config with legacy summary fields."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    store = SQLiteStateStore(db_path)
    config = await store.ensure_conversation_config(conversation_id)
    mounts = await get_conversation_mounts(db_path, conversation_id)
    mounted_library_ids = [mount["library_id"] for mount in mounts]
    write_library_id = next(
        (mount["library_id"] for mount in mounts if mount.get("is_write_target")),
        mounted_library_ids[0] if mounted_library_ids else "lib_default",
    )
    template = await store.get_conversation_template(conversation_id)
    _, item_count = await store.list_items(conversation_id, status="active", limit=1)
    data = config.to_dict()
    data.update({
        "mounted_library_ids": mounted_library_ids,
        "write_library_id": write_library_id,
        "mounts": mounts,
        "template_id": data.get("template_id") or (template.template_id if template else None),
        "template_name": template.name if template else None,
        "state_item_count": item_count,
        "is_new_session": item_count == 0 and mounted_library_ids == ["lib_default"],
    })
    return data


@router.put("/admin/conversations/{conversation_id}/config")
async def update_conversation_config_api(conversation_id: str, request: Request, data: dict = Body(...)):
    """Update policy config for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import set_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    payload = dict(data)
    payload["conversation_id"] = conversation_id
    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    store = SQLiteStateStore(db_path)
    if payload.get("template_id") and not await store.get_template(payload["template_id"]):
        raise HTTPException(status_code=404, detail="Template not found")
    if payload.get("table_template_id") and not await store.get_table_template(payload["table_template_id"]):
        raise HTTPException(status_code=404, detail="State table template not found")
    library_ids = payload.get("library_ids") or payload.get("mounted_library_ids") or []
    if library_ids:
        await set_conversation_mounts(
            db_path,
            conversation_id=conversation_id,
            library_ids=library_ids,
            write_library_id=payload.get("write_library_id"),
            user_id=payload.get("user_id"),
            character_id=payload.get("character_id"),
        )
    config = await store.set_conversation_config(payload)
    return {"status": "ok", "config": config.to_dict()}


@router.post("/admin/conversations/{conversation_id}/config")
async def post_conversation_config_api(conversation_id: str, request: Request, data: dict = Body(...)):
    return await update_conversation_config_api(conversation_id, request, data)


def _is_loopback(client_host: str | None) -> bool:
    if not client_host:
        return False
    return client_host in _LOOPBACK_HOSTS


def _require_admin(request: Request) -> None:
    """Require Bearer token only when ADMIN_TOKEN/admin_token is configured.

    Additional safeguard: when admin_token is empty AND the request comes from a non-loopback
    client, refuse access unless `server.allow_remote_access` is explicitly enabled. This
    prevents accidental data exposure when the GUI binds to 0.0.0.0 without setting a token.
    """
    from app.core.state import get_config

    cfg = get_config()
    token = cfg.server.get_admin_token()
    client_host = request.client.host if request.client else None
    if not token:
        if not _is_loopback(client_host) and not cfg.server.allow_remote_access:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Admin endpoint refused: no admin_token configured and remote access "
                    "not explicitly allowed (set server.allow_remote_access=true or "
                    "configure ADMIN_TOKEN)."
                ),
            )
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/health")
async def health(request: Request):
    from app.core.state import get_config

    cfg = get_config()
    actual_port = getattr(request.app.state, "actual_port", None)
    if actual_port is None:
        import os
        actual_port = os.getenv("KOKOROMEMO_ACTUAL_PORT")
    try:
        actual_port = int(actual_port) if actual_port else cfg.server.port
    except (TypeError, ValueError):
        actual_port = cfg.server.port
    return {
        "status": "ok",
        "server": "ok",
        "version": getattr(request.app.state, "app_version", "unknown"),
        "embedding": {
            "enabled": cfg.embedding.enabled,
            "model": cfg.embedding.model,
            "dimension": cfg.embedding.dimension,
        },
        "rerank": {
            "enabled": cfg.rerank.enabled,
            "model": cfg.rerank.model if cfg.rerank.enabled else None,
        },
        "llm": {"model": cfg.llm.model},
        "configured_port": cfg.server.port,
        "server_port": actual_port,
        "actual_port": actual_port,
    }


@router.get("/admin/stats")
async def get_stats(request: Request):
    """Return memory system statistics for the dashboard."""
    _require_admin(request)
    import aiosqlite
    from app.core.state import get_config

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    result: dict = {}

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT status, COUNT(*) FROM memory_cards GROUP BY status")
            result["cards_by_status"] = dict(await cursor.fetchall())

            cursor = await db.execute(
                "SELECT card_type, COUNT(*) FROM memory_cards WHERE status='approved' GROUP BY card_type"
            )
            result["cards_by_type"] = dict(await cursor.fetchall())

            cursor = await db.execute("SELECT COUNT(*) FROM memory_inbox WHERE status='pending'")
            row = await cursor.fetchone()
            result["inbox_pending"] = row[0] if row else 0

            cursor = await db.execute(
                "SELECT vector_synced, COUNT(*) FROM memory_cards WHERE status='approved' GROUP BY vector_synced"
            )
            result["sync_status"] = dict(await cursor.fetchall())

            cursor = await db.execute(
                "SELECT date(created_at) as day, COUNT(*) FROM memory_cards "
                "WHERE status='approved' AND created_at >= datetime('now', '-7 days') "
                "GROUP BY day ORDER BY day"
            )
            result["daily_growth"] = [{"date": r[0], "count": r[1]} for r in await cursor.fetchall()]

            cursor = await db.execute(
                "SELECT should_retrieve, COUNT(*) FROM retrieval_decisions "
                "WHERE created_at >= datetime('now', '-24 hours') GROUP BY should_retrieve"
            )
            result["gate_stats_24h"] = dict(await cursor.fetchall())
    except Exception:
        result.setdefault("cards_by_status", {})
        result.setdefault("inbox_pending", 0)

    return result


async def _fetch_models_from_remote(base_url: str, api_key: str, provider: str | None = None):
    """Fetch available models from a remote models endpoint."""
    if not api_key:
        return {"status": "error", "message": "未提供 API Key", "models": []}

    base_url = base_url.rstrip("/")
    is_gemini = provider == "gemini" or "googleapis.com" in base_url or "generativelanguage" in base_url
    is_anthropic = provider == "anthropic" or "anthropic.com" in base_url

    if is_gemini:
        url = base_url + "/models?key=" + api_key
        headers = {}
    elif is_anthropic:
        url = base_url + "/models"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        url = base_url + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                body = resp.text[:200]
                return {"status": "error", "message": f"远端返回 HTTP {resp.status_code}: {body}", "models": []}
            data = resp.json()

            models = []
            if is_gemini:
                for item in data.get("models", []):
                    if isinstance(item, dict) and "name" in item:
                        name = item["name"]
                        if name.startswith("models/"):
                            name = name[7:]
                        models.append(name)
            else:
                items = data.get("data", []) if isinstance(data, dict) else []
                for item in items:
                    if isinstance(item, dict) and "id" in item:
                        models.append(item["id"])
                    elif isinstance(item, str):
                        models.append(item)

            return {"status": "ok", "models": sorted(models)}
    except httpx.TimeoutException:
        return {"status": "error", "message": "请求超时，请检查 Base URL", "models": []}
    except Exception as e:
        return {"status": "error", "message": str(e), "models": []}


@router.post("/admin/fetch-models")
async def fetch_models(data: dict = Body(...)):
    """Fetch remote models without putting API keys in URLs."""
    return await _fetch_models_from_remote(data.get("base_url", ""), data.get("api_key", ""), data.get("provider"))


@router.get("/admin/config")
async def get_current_config(request: Request):
    """Return current configuration (safe fields only)."""
    from app.core.services import resolve_lancedb_path
    from app.core.state import get_config

    cfg = get_config()
    import os
    actual_port = getattr(request.app.state, "actual_port", None)
    actual_port = os.getenv("KOKOROMEMO_ACTUAL_PORT") or actual_port or cfg.server.port
    try:
        actual_port = int(actual_port)
    except (TypeError, ValueError):
        actual_port = cfg.server.port
    llm_key = cfg.llm.get_api_key()
    embedding_key = cfg.embedding.get_api_key()
    rerank_key = cfg.rerank.get_api_key()
    return {
        "server": {
            "host": cfg.server.host,
            "port": cfg.server.port,
            "actual_port": actual_port,
            "webui_port": cfg.server.webui_port,
            "timezone": cfg.server.timezone,
        },
        "storage": {"root_dir": cfg.storage.root_dir},
        "vector_index": {"path": resolve_lancedb_path(cfg), "table": cfg.storage.lancedb.table},
        "embedding": {
            "enabled": cfg.embedding.enabled,
            "provider": cfg.embedding.provider,
            "base_url": cfg.embedding.base_url,
            "api_key": cfg.embedding.api_key,
            "api_key_set": bool(embedding_key),
            "model": cfg.embedding.model,
            "dimension": cfg.embedding.dimension,
        },
        "rerank": {
            "enabled": cfg.rerank.enabled,
            "provider": cfg.rerank.provider,
            "base_url": cfg.rerank.base_url,
            "api_key": cfg.rerank.api_key,
            "api_key_set": bool(rerank_key),
            "model": cfg.rerank.model,
            "max_documents_per_request": cfg.rerank.max_documents_per_request,
        },
        "memory": {
            "enabled": cfg.memory.enabled,
            "inject_enabled": cfg.memory.inject_enabled,
            "extraction_enabled": cfg.memory.extraction_enabled,
            "max_recent_turns_for_query": cfg.memory.max_recent_turns_for_query,
            "vector_top_k": cfg.memory.vector_top_k,
            "final_top_k": cfg.memory.final_top_k,
            "max_injected_chars": cfg.memory.max_injected_chars,
            "scopes": {
                "include_global": cfg.memory.scopes.include_global,
                "include_character": cfg.memory.scopes.include_character,
                "include_conversation": cfg.memory.scopes.include_conversation,
            },
            "scoring": {
                "vector_weight": cfg.memory.scoring.vector_weight,
                "importance_weight": cfg.memory.scoring.importance_weight,
                "recency_weight": cfg.memory.scoring.recency_weight,
                "scope_weight": cfg.memory.scoring.scope_weight,
                "confidence_weight": cfg.memory.scoring.confidence_weight,
            },
            "extraction": {
                "min_importance": cfg.memory.extraction.min_importance,
                "min_confidence": cfg.memory.extraction.min_confidence,
                "extract_after_each_turn": cfg.memory.extraction.extract_after_each_turn,
                "fallback_rule_based": cfg.memory.extraction.fallback_rule_based,
            },
            "hot_context": {
                "enabled": cfg.memory.hot_context.enabled,
                "inject_always": cfg.memory.hot_context.inject_always,
                "max_chars": cfg.memory.hot_context.max_chars,
                "include_sections": dict(cfg.memory.hot_context.include_sections),
                "section_order": list(cfg.memory.hot_context.section_order),
                "max_items_per_section": dict(cfg.memory.hot_context.max_items_per_section),
            },
            "retrieval_gate": {
                "enabled": cfg.memory.retrieval_gate.enabled,
                "mode": cfg.memory.retrieval_gate.mode,
                "vector_search_on_new_session": cfg.memory.retrieval_gate.vector_search_on_new_session,
                "vector_search_every_n_turns": cfg.memory.retrieval_gate.vector_search_every_n_turns,
                "vector_search_when_state_confidence_below": cfg.memory.retrieval_gate.vector_search_when_state_confidence_below,
                "trigger_keywords": list(cfg.memory.retrieval_gate.trigger_keywords),
                "skip_when_latest_user_text_chars_below": cfg.memory.retrieval_gate.skip_when_latest_user_text_chars_below,
                "skip_when_state_is_sufficient": cfg.memory.retrieval_gate.skip_when_state_is_sufficient,
            },
            "judge": {
                "enabled": cfg.memory.judge.enabled,
                "provider": cfg.memory.judge.provider,
                "base_url": cfg.memory.judge.base_url,
                "api_key": cfg.memory.judge.api_key,
                "api_key_set": bool(cfg.memory.judge.get_api_key()),
                "model": cfg.memory.judge.model,
                "timeout_seconds": cfg.memory.judge.timeout_seconds,
                "temperature": cfg.memory.judge.temperature,
                "mode": cfg.memory.judge.mode,
                "user_rules": cfg.memory.judge.user_rules,
                "prompt": cfg.memory.judge.prompt,
            },
            "state_updater": {
                "enabled": cfg.memory.state_updater.enabled,
                "mode": cfg.memory.state_updater.mode,
                "update_after_each_turn": cfg.memory.state_updater.update_after_each_turn,
                "update_every_n_turns": cfg.memory.state_updater.update_every_n_turns,
                "min_confidence": cfg.memory.state_updater.min_confidence,
                "max_state_items_per_conversation": cfg.memory.state_updater.max_state_items_per_conversation,
                "provider": cfg.memory.state_updater.provider,
                "base_url": cfg.memory.state_updater.base_url,
                "api_key": cfg.memory.state_updater.api_key,
                "api_key_set": bool(cfg.memory.state_updater.get_api_key()),
                "model": cfg.memory.state_updater.model,
                "timeout_seconds": cfg.memory.state_updater.timeout_seconds,
                "temperature": cfg.memory.state_updater.temperature,
                "prompt": cfg.memory.state_updater.prompt,
            },
        },
        "llm": {
            "forward_mode": cfg.llm.forward_mode,
            "provider": cfg.llm.provider,
            "base_url": cfg.llm.base_url,
            "api_key": cfg.llm.api_key,
            "api_key_set": bool(llm_key),
            "model": cfg.llm.model,
        },
        "conversation": {
            "auto_new_session_gap_minutes": cfg.conversation.auto_new_session_gap_minutes,
            "detect_system_prompt_change": cfg.conversation.detect_system_prompt_change,
            "detect_message_count_reset": cfg.conversation.detect_message_count_reset,
        },
    }


@router.post("/admin/config")
async def save_config(data: dict = Body(...)):
    """Save configuration to config.yaml and reload."""
    from app.core.config import load_config, resolve_config_path
    from app.core.services import reset_services
    from app.core.state import get_config, set_config

    cfg = get_config()

    # 查找配置文件路径
    config_path = resolve_config_path()

    # 读取现有 YAML
    existing = {}
    if config_path and config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            existing = yaml.safe_load(f) or {}

    # 检测需要重启的字段是否变更
    old_root_dir = cfg.storage.root_dir
    old_port = cfg.server.port

    # 将传入数据合并到现有配置（对嵌套字典做深度合并）
    def _deep_merge(target: dict, src: dict) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(target.get(k), dict):
                _deep_merge(target[k], v)
            else:
                target[k] = v

    def _drop_empty_api_keys(section: dict | None) -> None:
        """避免设置页未重新填写密钥时，用空字符串覆盖已经保存的 API Key。"""
        if isinstance(section, dict) and section.get("api_key") == "":
            section.pop("api_key", None)

    _drop_empty_api_keys(data.get("llm"))
    _drop_empty_api_keys(data.get("embedding"))
    _drop_empty_api_keys(data.get("rerank"))
    if isinstance(data.get("memory"), dict):
        _drop_empty_api_keys(data["memory"].get("judge"))
        _drop_empty_api_keys(data["memory"].get("state_updater"))

    if "server" in data:
        existing.setdefault("server", {}).update(data["server"])
    if "llm" in data:
        existing.setdefault("llm", {}).update(data["llm"])
    if "embedding" in data:
        existing.setdefault("embedding", {}).update(data["embedding"])
    if "rerank" in data:
        existing.setdefault("rerank", {}).update(data["rerank"])
    if "memory" in data:
        _deep_merge(existing.setdefault("memory", {}), data["memory"])
    if "conversation" in data:
        existing.setdefault("conversation", {}).update(data["conversation"])
    if "storage" in data:
        new_root = data["storage"].get("root_dir")
        existing.setdefault("storage", {}).update(data["storage"])

        # root_dir 变更时，同步更新 YAML 中的子路径以保持一致
        if new_root and new_root != old_root_dir:
            default_root = "./data"
            default_prefix = default_root + "/"
            storage = existing["storage"]
            sqlite = storage.get("sqlite", {})
            for key in ("app_db", "memory_db"):
                val = sqlite.get(key, "")
                if val.startswith(default_prefix):
                    suffix = val[len(default_prefix):]
                    sqlite[key] = str(Path(new_root) / suffix)
            lancedb = storage.get("lancedb", {})
            ldb_val = lancedb.get("path", "")
            if ldb_val.startswith(default_prefix):
                suffix = ldb_val[len(default_prefix):]
                lancedb["path"] = str(Path(new_root) / suffix)

    # 写入当前生效的 config.yaml，而不是任意进程工作目录。
    out_path = resolve_config_path(for_write=True) or Path("config.yaml").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(existing, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 重新加载内存中的配置
    new_cfg = load_config(str(out_path))
    set_config(new_cfg)
    from app.core.time_util import set_configured_timezone
    set_configured_timezone(new_cfg.server.timezone or None)
    reset_services()

    # 检查是否需要重启
    needs_restart = (
        new_cfg.storage.root_dir != old_root_dir
        or new_cfg.server.port != old_port
    )

    if needs_restart:
        import logging
        logger = logging.getLogger("kokoromemo")
        logger.info("配置变更需要重启服务（存储目录或端口已更改）")
        return {"status": "restart_required", "message": "配置已保存，正在重启服务..."}

    return {"status": "ok", "message": "配置已保存并生效"}


@router.get("/admin/memories")
async def list_memories(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    library_id: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    character_id: str | None = Query(default=None),
    status: str = Query(default="approved"),
):
    """List memory cards."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import init_cards_db
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    await init_cards_db(db_path)

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            where_clauses = ["status = ?"]
            params: list = [status]

            if scope:
                where_clauses.append("scope = ?")
                params.append(scope)
            if library_id:
                where_clauses.append("library_id = ?")
                params.append(library_id)
            if character_id:
                where_clauses.append("character_id = ?")
                params.append(character_id)

            where_sql = " AND ".join(where_clauses)

            count_cursor = await db.execute(
                f"SELECT COUNT(*) FROM memory_cards WHERE {where_sql}",
                params,
            )
            count_row = await count_cursor.fetchone()
            total = count_row[0] if count_row else 0

            params.extend([limit, offset])
            cursor = await db.execute(
                f"SELECT * FROM memory_cards WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            )
            rows = await cursor.fetchall()

            memories = []
            for r in rows:
                memories.append({
                    "memory_id": r["card_id"],
                    "card_id": r["card_id"],
                    "library_id": r["library_id"],
                    "user_id": r["user_id"],
                    "character_id": r["character_id"],
                    "conversation_id": r["conversation_id"],
                    "scope": r["scope"],
                    "memory_type": r["card_type"],
                    "content": r["content"],
                    "summary": r["summary"],
                    "importance": r["importance"],
                    "confidence": r["confidence"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "access_count": r["access_count"],
                })

            return {"memories": memories, "total": total, "limit": limit, "offset": offset}
    except Exception:
        return {"memories": [], "total": 0, "limit": limit, "offset": offset}


@router.get("/admin/characters")
async def list_characters_api(request: Request):
    """List all known characters with their default configurations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_characters

    cfg = get_config()
    items = await list_characters(cfg.storage.sqlite.app_db)
    return {"items": items}


@router.get("/admin/characters/{character_id}")
async def get_character_api(character_id: str, request: Request):
    """Get one character profile and default strategy."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_characters

    cfg = get_config()
    for item in await list_characters(cfg.storage.sqlite.app_db):
        if item.get("character_id") == character_id:
            return item
    raise HTTPException(status_code=404, detail="Character not found")


@router.put("/admin/characters/{character_id}")
async def update_character_api(character_id: str, request: Request, data: dict = Body(...)):
    """Update character profile fields."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import update_character_profile

    cfg = get_config()
    await update_character_profile(
        cfg.storage.sqlite.app_db,
        character_id,
        display_name=data.get("display_name"),
        aliases=data.get("aliases") or [],
        notes=data.get("notes"),
        source=data.get("source"),
        user_id=data.get("user_id") or "default",
    )
    return {"status": "ok", "character_id": character_id}


@router.get("/admin/characters/{character_id}/conversations")
async def list_character_conversations_api(character_id: str, request: Request):
    """List conversations associated with one character, including state config when present."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_character_conversations
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    items = []
    for conv in await list_character_conversations(cfg.storage.sqlite.app_db, character_id):
        config = await store.get_conversation_config(conv["conversation_id"])
        row = dict(conv)
        row["config"] = config.to_dict() if config else None
        items.append(row)
    return {"items": items}


@router.get("/admin/conversations/{conversation_id}/preview")
async def preview_conversation_api(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
):
    """Return recent messages for quick conversation ownership preview."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_conversations
    from app.storage.sqlite_conversation import get_recent_messages

    cfg = get_config()
    conversations, _ = await list_conversations(cfg.storage.sqlite.app_db, limit=500, offset=0)
    conversation = next((item for item in conversations if item.get("conversation_id") == conversation_id), None)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    chat_db_path = str(Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite"))
    messages = await get_recent_messages(chat_db_path, conversation_id, limit=limit) if Path(chat_db_path).exists() else []
    return {"conversation": conversation, "messages": messages}


@router.get("/admin/discovered-characters")
async def discover_characters_api(request: Request):
    """Discover characters from conversations and merge default configs."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import discover_characters

    cfg = get_config()
    items = await discover_characters(cfg.storage.sqlite.app_db)
    return {"items": items}


@router.get("/admin/characters/{character_id}/defaults")
async def get_character_defaults_api(character_id: str, request: Request):
    """Get default config for a character."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import get_character_defaults

    cfg = get_config()
    defaults = await get_character_defaults(cfg.storage.sqlite.app_db, character_id)
    if not defaults:
        return {"character_id": character_id, "template_id": None, "library_ids": None, "write_library_id": None, "auto_apply": True}
    return defaults


@router.post("/admin/characters/{character_id}/defaults")
async def set_character_defaults_api(character_id: str, request: Request, data: dict = Body(...)):
    """Set default template and library config for a character."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import set_character_defaults

    cfg = get_config()
    await set_character_defaults(
        cfg.storage.sqlite.app_db,
        character_id,
        profile_id=data.get("profile_id"),
        template_id=data.get("template_id"),
        table_template_id=data.get("table_template_id"),
        mount_preset_id=data.get("mount_preset_id"),
        memory_write_policy=data.get("memory_write_policy"),
        state_update_policy=data.get("state_update_policy"),
        injection_policy=data.get("injection_policy"),
        library_ids=data.get("library_ids"),
        write_library_id=data.get("write_library_id"),
        auto_apply=data.get("auto_apply", True),
    )
    return {"status": "ok", "character_id": character_id}


@router.put("/admin/characters/{character_id}/defaults")
async def put_character_defaults_api(character_id: str, request: Request, data: dict = Body(...)):
    return await set_character_defaults_api(character_id, request, data)


@router.post("/admin/characters/{character_id}/apply-defaults")
async def apply_character_defaults_api(character_id: str, request: Request, data: dict = Body(default_factory=dict)):
    """Apply character default mounts and conversation config to existing conversations."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import get_character_defaults, list_character_conversations
    from app.storage.sqlite_cards import set_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    defaults = await get_character_defaults(cfg.storage.sqlite.app_db, character_id)
    if not defaults:
        raise HTTPException(status_code=404, detail="Character defaults not found")

    selected = set(data.get("conversation_ids") or [])
    conversations = await list_character_conversations(cfg.storage.sqlite.app_db, character_id)
    if selected:
        conversations = [item for item in conversations if item["conversation_id"] in selected]

    apply_policy = data.get("apply_policy", True)
    apply_mounts = data.get("apply_mounts", True)
    overwrite_existing = data.get("overwrite_existing", True)
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    updated = 0
    for conv in conversations:
        conversation_id = conv["conversation_id"]
        if apply_mounts:
            library_ids = defaults.get("library_ids") or ["lib_default"]
            await set_conversation_mounts(
                cfg.storage.sqlite.memory_db,
                conversation_id,
                library_ids,
                defaults.get("write_library_id") or library_ids[0],
            )
        if apply_policy:
            existing = await store.get_conversation_config(conversation_id)
            if overwrite_existing or not existing:
                await store.set_conversation_config({
                    "conversation_id": conversation_id,
                    "profile_id": defaults.get("profile_id"),
                    "template_id": defaults.get("template_id"),
                    "table_template_id": defaults.get("table_template_id"),
                    "mount_preset_id": defaults.get("mount_preset_id"),
                    "memory_write_policy": defaults.get("memory_write_policy"),
                    "state_update_policy": defaults.get("state_update_policy"),
                    "injection_policy": defaults.get("injection_policy"),
                    "created_from_default": True,
                })
        updated += 1
    return {"status": "ok", "updated": updated}


@router.get("/admin/characters/{character_id}/export")
async def export_character_config_api(character_id: str, request: Request):
    """Export one character profile and default strategy."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import get_character_defaults, list_characters

    cfg = get_config()
    character = None
    for item in await list_characters(cfg.storage.sqlite.app_db):
        if item.get("character_id") == character_id:
            character = item
            break
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return {
        "version": 1,
        "character": character,
        "defaults": await get_character_defaults(cfg.storage.sqlite.app_db, character_id),
    }


@router.post("/admin/characters/import")
async def import_character_config_api(request: Request, data: dict = Body(...)):
    """Import one character profile and default strategy."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import set_character_defaults, update_character_profile

    cfg = get_config()
    character = data.get("character") or {}
    defaults = data.get("defaults") or {}
    character_id = data.get("target_character_id") or character.get("character_id") or defaults.get("character_id")
    if not character_id:
        raise HTTPException(status_code=400, detail="character_id is required")
    await update_character_profile(
        cfg.storage.sqlite.app_db,
        character_id,
        display_name=character.get("display_name"),
        aliases=character.get("aliases") or [],
        notes=character.get("notes"),
        source=character.get("source"),
        user_id=character.get("user_id") or "default",
    )
    await set_character_defaults(
        cfg.storage.sqlite.app_db,
        character_id,
        profile_id=defaults.get("profile_id"),
        template_id=defaults.get("template_id"),
        table_template_id=defaults.get("table_template_id"),
        mount_preset_id=defaults.get("mount_preset_id"),
        memory_write_policy=defaults.get("memory_write_policy"),
        state_update_policy=defaults.get("state_update_policy"),
        injection_policy=defaults.get("injection_policy"),
        library_ids=defaults.get("library_ids"),
        write_library_id=defaults.get("write_library_id"),
        auto_apply=defaults.get("auto_apply", True),
    )
    return {"status": "ok", "character_id": character_id}


@router.get("/admin/memory-libraries")
async def list_memory_libraries_api():
    """List long-term memory libraries."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import list_memory_libraries

    cfg = get_config()
    items = await list_memory_libraries(cfg.storage.sqlite.memory_db)
    return {"items": items}


@router.post("/admin/memory-libraries")
async def create_memory_library_api(data: dict = Body(...)):
    """Create a memory library or save selected libraries as a new preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_memory_library

    cfg = get_config()
    library_id = await create_memory_library(
        cfg.storage.sqlite.memory_db,
        name=data.get("name") or "未命名记忆库",
        description=data.get("description", ""),
        source_library_ids=data.get("source_library_ids") or [],
    )
    return {"status": "ok", "library_id": library_id}


@router.put("/admin/memory-libraries/{library_id}")
async def update_memory_library_api(library_id: str, data: dict = Body(...)):
    """Rename or describe a memory library."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import update_memory_library

    cfg = get_config()
    ok = await update_memory_library(
        cfg.storage.sqlite.memory_db,
        library_id=library_id,
        name=data.get("name") or "未命名记忆库",
        description=data.get("description", ""),
    )
    return {"status": "ok" if ok else "error", "message": None if ok else "记忆库不存在"}


@router.delete("/admin/memory-libraries/{library_id}")
async def delete_memory_library_api(library_id: str):
    """Soft-delete a custom memory library."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import delete_memory_library

    cfg = get_config()
    ok = await delete_memory_library(cfg.storage.sqlite.memory_db, library_id)
    return {"status": "ok" if ok else "error", "message": None if ok else "默认记忆库不能删除或记忆库不存在"}


@router.get("/admin/conversations")
async def list_conversations_api(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List recent conversations ordered by last activity."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_conversations

    cfg = get_config()
    items, total = await list_conversations(cfg.storage.sqlite.app_db, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/admin/conversations/{conversation_id}")
async def update_conversation_profile_api(conversation_id: str, request: Request, data: dict = Body(...)):
    """Update user-facing conversation profile fields."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import update_conversation_profile

    cfg = get_config()
    old_item = next((item for item in (await list_conversations(cfg.storage.sqlite.app_db, limit=500, offset=0))[0] if item.get("conversation_id") == conversation_id), None)
    item = await update_conversation_profile(
        cfg.storage.sqlite.app_db,
        conversation_id,
        title=data.get("title") if "title" in data else None,
        character_id=data.get("character_id") if "character_id" in data else None,
    )
    if not item:
        return {"status": "error", "message": "会话不存在或没有可更新字段"}
    sync_result = None
    if "character_id" in data and (old_item or {}).get("character_id") != item.get("character_id"):
        from pathlib import Path
        from app.storage.sqlite_cards import update_conversation_character_refs
        from app.storage.sqlite_conversation import update_conversation_character
        from app.storage.sqlite_state import SQLiteStateStore

        chat_db_path = str(Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite"))
        sync_result = {
            "app": 1,
            "chat_turns": await update_conversation_character(chat_db_path, conversation_id, item.get("character_id")),
            "memory": await update_conversation_character_refs(cfg.storage.sqlite.memory_db, conversation_id, item.get("character_id")),
            "state": await SQLiteStateStore(cfg.storage.sqlite.memory_db).update_conversation_character_refs(conversation_id, item.get("character_id")),
        }
    return {"status": "ok", "item": item, "sync": sync_result}


@router.delete("/admin/conversations/{conversation_id}")
async def delete_conversation_api(conversation_id: str, request: Request):
    """Delete a conversation record."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import delete_conversation

    cfg = get_config()
    ok = await delete_conversation(cfg.storage.sqlite.app_db, conversation_id)
    return {"status": "ok" if ok else "error", "message": None if ok else "会话不存在"}


@router.get("/admin/conversations/{conversation_id}/memory-mounts")
async def get_conversation_memory_mounts_api(conversation_id: str):
    """Get mounted long-term memory libraries for a conversation."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_conversation_mounts

    cfg = get_config()
    mounts = await get_conversation_mounts(cfg.storage.sqlite.memory_db, conversation_id)
    return {"items": mounts}


@router.post("/admin/conversations/{conversation_id}/memory-mounts")
async def set_conversation_memory_mounts_api(conversation_id: str, data: dict = Body(...)):
    """Set mounted long-term memory libraries for a conversation."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import set_conversation_mounts

    cfg = get_config()
    library_ids = data.get("library_ids") or []
    await set_conversation_mounts(
        cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        library_ids=library_ids,
        write_library_id=data.get("write_library_id"),
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
    )
    return {"status": "ok"}


@router.post("/admin/memories")
async def create_memory_card(data: dict = Body(...)):
    """Manually create an approved memory card."""
    from app.core.ids import generate_id
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_card, insert_card_version
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    card_id = generate_id("card_")
    await insert_card(
        db_path,
        card_id=card_id,
        library_id=data.get("library_id"),
        user_id=data.get("user_id") or "default_user",
        character_id=data.get("character_id"),
        conversation_id=data.get("conversation_id"),
        scope=data.get("scope", "global"),
        card_type=data.get("card_type", "preference"),
        title=data.get("title"),
        content=data.get("content", ""),
        summary=data.get("summary"),
        importance=float(data.get("importance", 0.5)),
        confidence=float(data.get("confidence", 0.7)),
        status=data.get("status", "approved"),
        is_pinned=1 if data.get("is_pinned") else 0,
        evidence_text=data.get("evidence_text"),
    )
    await insert_card_version(
        db_path,
        card_id=card_id,
        content=data.get("content", ""),
        card_type=data.get("card_type", "preference"),
        summary=data.get("summary"),
        importance=float(data.get("importance", 0.5)),
        confidence=float(data.get("confidence", 0.7)),
    )
    if data.get("status", "approved") == "approved":
        ep = get_embedding_provider(cfg)
        store = get_lancedb_store(cfg)
        if ep and store:
            try:
                await sync_card_vector(db_path, card_id, ep, store)
            except Exception as exc:
                await enqueue_card_vector_sync(db_path, card_id, str(exc))
    return {"status": "ok", "card_id": card_id}


@router.put("/admin/memories/{card_id}")
async def update_memory_card(card_id: str, data: dict = Body(...)):
    """Edit a memory card's content, type, or importance."""
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_card_version, mark_card_vector_unsynced
    from app.storage.vector_sync import enqueue_card_vector_sync, sync_card_vector
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    allowed_fields = {"library_id", "content", "card_type", "scope", "importance", "confidence", "title", "summary", "is_pinned"}
    updates = {k: v for k, v in data.items() if k in allowed_fields}
    if not updates:
        return {"status": "error", "message": "无可更新字段"}

    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [card_id]

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            f"UPDATE memory_cards SET {set_clauses}, updated_at = datetime('now', 'localtime') WHERE card_id = ?",
            values,
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM memory_cards WHERE card_id = ?", (card_id,))
        row = await cursor.fetchone()

    if row and row["status"] == "approved":
        await insert_card_version(
            db_path,
            card_id=row["card_id"],
            content=row["content"],
            card_type=row["card_type"],
            summary=row["summary"],
            importance=row["importance"],
            confidence=row["confidence"],
        )
        ep = get_embedding_provider(cfg)
        store = get_lancedb_store(cfg)
        if ep and store:
            try:
                await sync_card_vector(db_path, card_id, ep, store)
            except Exception as exc:
                await mark_card_vector_unsynced(db_path, card_id)
                await enqueue_card_vector_sync(db_path, card_id, str(exc))

    return {"status": "ok", "card_id": card_id}


@router.delete("/admin/memories/{card_id}")
async def delete_memory_card(card_id: str):
    """Soft-delete a memory card."""
    from app.core.services import get_lancedb_store
    from app.core.state import get_config
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_cards SET status = 'deleted', updated_at = datetime('now', 'localtime') WHERE card_id = ?",
            (card_id,),
        )
        await db.commit()

    store = get_lancedb_store(cfg)
    if store:
        try:
            store.delete(f"memory_id = '{card_id}'")
        except Exception:
            pass

    return {"status": "ok"}


@router.post("/admin/memories/{card_id}/deprecate")
async def deprecate_memory_card(card_id: str, note: str = Body(default="")):
    """Mark a memory card as deprecated so it is no longer recalled by default."""
    from app.core.services import get_lancedb_store
    from app.core.state import get_config
    from app.storage.sqlite_cards import insert_review_action
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE memory_cards SET status = 'deprecated', updated_at = datetime('now', 'localtime') WHERE card_id = ?",
            (card_id,),
        )
        await db.commit()

    await insert_review_action(db_path, action="deprecate", card_id=card_id, note=note)

    store = get_lancedb_store(cfg)
    if store:
        try:
            store.delete(f"memory_id = '{card_id}'")
        except Exception:
            pass

    return {"status": "ok", "card_id": card_id}


@router.post("/admin/rebuild-vector-index")
async def rebuild_index():
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.rebuild_v2 import rebuild_vector_index_v2

    cfg = get_config()
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)
    if not ep or not store:
        return {"status": "error", "message": "Embedding or LanceDB not configured"}

    result = await rebuild_vector_index_v2(
        cfg.storage.sqlite.memory_db, store, ep, batch_size=cfg.embedding.batch_size,
    )
    return result


@router.get("/admin/index-migration-status")
async def get_index_migration_status_api(request: Request):
    """Check the status of an ongoing or completed index migration."""
    _require_admin(request)
    from app.core.services import get_index_migration_status

    status = get_index_migration_status()
    if not status:
        return {"status": "idle", "message": "No migration in progress"}
    return status


@router.post("/admin/start-index-migration")
async def start_index_migration_api(request: Request, data: dict = Body(default=None)):
    """Start an asynchronous embedding index migration with the current config."""
    _require_admin(request)
    from app.core.services import (
        get_index_migration_status,
        start_index_migration,
    )
    from app.core.state import get_config

    current = get_index_migration_status()
    if current and current.get("status") == "running":
        return {"status": "error", "message": "Migration already running"}

    payload = data or {}
    cfg = get_config()
    old_model = payload.get("old_model") or cfg.embedding.model
    old_dimension = payload.get("old_dimension") or cfg.embedding.dimension
    start_index_migration(cfg, old_model, old_dimension)
    return {"status": "ok", "message": "Migration started"}


# --- 待审核 API ---

@router.get("/admin/inbox")
async def list_inbox(
    status: str = Query(default="pending"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List memory inbox items."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_inbox_items

    cfg = get_config()
    items, total = await get_inbox_items(cfg.storage.sqlite.memory_db, status=status, limit=limit, offset=offset)
    return {"items": items, "total": total, "status": status}


@router.post("/admin/inbox/{inbox_id}/approve")
async def approve_inbox_item(inbox_id: str):
    """Approve an inbox item → create approved card + vector sync."""
    import json as json_mod
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.core.ids import generate_id
    from app.storage.sqlite_cards import (
        get_inbox_item, update_inbox_status, insert_card, insert_card_version,
        insert_review_action, get_write_library_id, transition_inbox_status,
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


@router.post("/admin/jobs/retry-vector-sync")
async def retry_vector_sync_jobs(limit: int = Query(default=50, le=200)):
    """Retry failed/pending card vector sync jobs."""
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.storage.vector_sync import retry_card_vector_sync_jobs

    cfg = get_config()
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)
    if not ep or not store:
        return {"status": "error", "message": "Embedding or LanceDB not configured"}
    return await retry_card_vector_sync_jobs(cfg.storage.sqlite.memory_db, ep, store, limit=limit)


# --- 会话状态 API ---

def _state_item_to_dict(item) -> dict:
    return {
        "item_id": item.item_id,
        "template_id": item.template_id,
        "tab_id": item.tab_id,
        "field_id": item.field_id,
        "field_key": item.field_key,
        "user_id": item.user_id,
        "character_id": item.character_id,
        "world_id": item.world_id,
        "conversation_id": item.conversation_id,
        "category": item.category,
        "item_key": item.item_key,
        "item_value": item.content,
        "content": item.content,
        "title": item.title,
        "status": item.status,
        "priority": item.priority,
        "user_locked": item.user_locked,
        "confidence": item.confidence,
        "source": item.source,
        "source_turn_ids": item.source_turn_ids,
        "source_message_ids": item.source_message_ids,
        "linked_card_ids": item.linked_card_ids,
        "linked_summary_ids": item.linked_summary_ids,
        "metadata": item.metadata,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "last_injected_at": item.last_injected_at,
        "expires_at": item.expires_at,
    }


def _field_to_dict(field) -> dict:
    return {
        "field_id": field.field_id,
        "template_id": field.template_id,
        "tab_id": field.tab_id,
        "field_key": field.field_key,
        "label": field.label,
        "field_type": field.field_type,
        "description": field.description,
        "ai_writable": field.ai_writable,
        "include_in_prompt": field.include_in_prompt,
        "sort_order": field.sort_order,
        "default_value": field.default_value,
        "options": field.options,
        "status": field.status,
    }


def _tab_to_dict(tab) -> dict:
    return {
        "tab_id": tab.tab_id,
        "template_id": tab.template_id,
        "tab_key": tab.tab_key,
        "label": tab.label,
        "description": tab.description,
        "sort_order": tab.sort_order,
        "fields": [_field_to_dict(field) for field in tab.fields],
    }


def _template_to_dict(template, include_tabs: bool = True) -> dict:
    data = {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "is_builtin": template.is_builtin,
        "status": template.status,
    }
    if include_tabs:
        data["tabs"] = [_tab_to_dict(tab) for tab in template.tabs]
    return data


def _state_table_column_to_dict(column) -> dict:
    return {
        "column_id": column.column_id,
        "table_id": column.table_id,
        "column_key": column.column_key,
        "name": column.name,
        "description": column.description,
        "value_type": column.value_type,
        "required": column.required,
        "sort_order": column.sort_order,
        "include_in_prompt": column.include_in_prompt,
        "max_chars": column.max_chars,
        "default_value": column.default_value,
        "options": column.options,
    }


def _state_table_schema_to_dict(table) -> dict:
    return {
        "table_id": table.table_id,
        "template_id": table.template_id,
        "table_key": table.table_key,
        "name": table.name,
        "description": table.description,
        "sort_order": table.sort_order,
        "enabled": table.enabled,
        "required": table.required,
        "as_status": table.as_status,
        "include_in_prompt": table.include_in_prompt,
        "max_prompt_rows": table.max_prompt_rows,
        "prompt_priority": table.prompt_priority,
        "insert_rule": table.insert_rule,
        "update_rule": table.update_rule,
        "delete_rule": table.delete_rule,
        "resolve_rule": table.resolve_rule,
        "note": table.note,
        "columns": [_state_table_column_to_dict(column) for column in table.columns],
    }


def _state_table_template_to_dict(template, include_tables: bool = True) -> dict:
    data = {
        "template_id": template.template_id,
        "name": template.name,
        "description": template.description,
        "scenario_type": template.scenario_type,
        "is_builtin": template.is_builtin,
        "status": template.status,
        "version": template.version,
    }
    if include_tables:
        data["tables"] = [_state_table_schema_to_dict(table) for table in template.tables]
    return data


def _state_table_row_to_dict(row) -> dict:
    return {
        "row_id": row.row_id,
        "conversation_id": row.conversation_id,
        "template_id": row.template_id,
        "table_id": row.table_id,
        "table_key": row.table_key,
        "status": row.status,
        "priority": row.priority,
        "confidence": row.confidence,
        "source": row.source,
        "source_turn_id": row.source_turn_id,
        "source_message_ids": row.source_message_ids,
        "metadata": row.metadata,
        "cells": {key: {"cell_id": cell.cell_id, "value": cell.value, "confidence": cell.confidence, "updated_at": cell.updated_at} for key, cell in row.cells.items()},
        "values": {key: cell.value for key, cell in row.cells.items()},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _template_from_payload(data: dict):
    from app.memory.state_schema import StateBoardField, StateBoardTab, StateBoardTemplate

    template = StateBoardTemplate(
        template_id=data.get("template_id"),
        name=data.get("name", "未命名模板"),
        description=data.get("description", ""),
        is_builtin=bool(data.get("is_builtin", False)),
        status=data.get("status", "active"),
    )
    for tab_data in data.get("tabs", []):
        tab = StateBoardTab(
            tab_id=tab_data.get("tab_id"),
            template_id=template.template_id or "",
            tab_key=tab_data.get("tab_key") or tab_data.get("label") or "tab",
            label=tab_data.get("label") or tab_data.get("tab_key") or "标签页",
            description=tab_data.get("description", ""),
            sort_order=int(tab_data.get("sort_order", 0)),
        )
        for field_data in tab_data.get("fields", []):
            tab.fields.append(StateBoardField(
                field_id=field_data.get("field_id"),
                template_id=template.template_id or "",
                tab_id=tab.tab_id or "",
                field_key=field_data.get("field_key") or field_data.get("label") or "field",
                label=field_data.get("label") or field_data.get("field_key") or "字段",
                field_type=field_data.get("field_type", "multiline"),
                description=field_data.get("description", ""),
                ai_writable=bool(field_data.get("ai_writable", True)),
                include_in_prompt=bool(field_data.get("include_in_prompt", True)),
                sort_order=int(field_data.get("sort_order", 0)),
                default_value=field_data.get("default_value", ""),
                options=field_data.get("options", {}),
                status=field_data.get("status", "active"),
            ))
        template.tabs.append(tab)
    return template


def _template_import_payload(data: dict) -> dict:
    """Return a custom-template payload with all persistent IDs stripped."""
    import copy

    payload = copy.deepcopy(data)
    payload.pop("template_id", None)
    payload["is_builtin"] = False
    for tab in payload.get("tabs", []):
        tab.pop("tab_id", None)
        for field in tab.get("fields", []):
            field.pop("field_id", None)
    return payload


@router.get("/admin/state/templates")
async def list_state_templates(request: Request):
    """List available state board templates."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    templates = await store.list_templates()
    return {"items": [_template_to_dict(template, include_tabs=False) for template in templates]}


@router.get("/admin/state/table-templates")
async def list_state_table_templates(request: Request):
    """List available table-based state board templates."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    templates = await store.list_table_templates()
    return {"items": [_state_table_template_to_dict(template, include_tables=False) for template in templates]}


@router.get("/admin/state/table-templates/{template_id}")
async def get_state_table_template(template_id: str, request: Request):
    """Get a full table-based state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_table_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="State table template not found")
    return _state_table_template_to_dict(template)


@router.get("/admin/state/templates/{template_id}")
async def get_state_template(template_id: str, request: Request):
    """Get a full state board template with item counts per tab."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    result = _template_to_dict(template)
    for tab_dict in result.get("tabs", []):
        tab_dict["item_count"] = await store.count_items_for_tab(tab_dict["tab_id"])
    return result


@router.post("/admin/state/templates")
async def create_state_template(request: Request, data: dict = Body(...)):
    """Create or update a custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template_id = await SQLiteStateStore(get_config().storage.sqlite.memory_db).save_template(_template_from_payload(data))
    return {"status": "ok", "template_id": template_id}


@router.delete("/admin/state/templates/{template_id}")
async def delete_state_template(template_id: str, request: Request):
    """Soft-delete a custom state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    ok = await SQLiteStateStore(get_config().storage.sqlite.memory_db).update_template_status(template_id, "deleted")
    return {"status": "ok" if ok else "error", "message": None if ok else "内置模板不能删除或模板不存在"}


@router.post("/admin/state/templates/{template_id}/clone")
async def clone_state_template(template_id: str, request: Request):
    """Clone a template (used to create a custom copy of a built-in template)."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    new_id = await SQLiteStateStore(get_config().storage.sqlite.memory_db).clone_template(template_id)
    if not new_id:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "ok", "template_id": new_id}


@router.patch("/admin/state/templates/{template_id}/tabs/{tab_id}")
async def rename_state_template_tab(template_id: str, tab_id: str, request: Request, data: dict = Body(...)):
    """Rename a tab in a state board template."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    new_label = data.get("label", "").strip()
    if not new_label:
        raise HTTPException(status_code=400, detail="label is required")
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    tab_found = False
    for tab in template.tabs:
        if tab.tab_id == tab_id:
            tab.label = new_label
            tab_found = True
            break
    if not tab_found:
        raise HTTPException(status_code=404, detail="Tab not found")
    await store.save_template(template)
    return {"status": "ok"}


@router.get("/admin/conversations/{conversation_id}/state/template")
async def get_conversation_state_template(conversation_id: str, request: Request):
    """Get the template selected for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template = await SQLiteStateStore(get_config().storage.sqlite.memory_db).get_conversation_template(conversation_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_dict(template)


@router.post("/admin/conversations/{conversation_id}/state/template")
async def set_conversation_state_template(conversation_id: str, request: Request, data: dict = Body(...)):
    """Select a state board template for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template_id = data.get("template_id")
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id is required")
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    if not await store.get_template(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    await store.set_conversation_template(conversation_id, template_id)
    return {"status": "ok", "template_id": template_id}


@router.get("/admin/conversations/{conversation_id}/state")
async def get_conversation_state(
    conversation_id: str,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=200, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List hot-state items for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    items, total = await store.list_items(conversation_id, status=status, limit=limit, offset=offset)
    return {"items": [_state_item_to_dict(item) for item in items], "total": total, "limit": limit, "offset": offset}


@router.get("/admin/conversations/{conversation_id}/state/tables")
async def get_conversation_state_tables(conversation_id: str, request: Request):
    """Return the table-based state board for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_conversation_table_template(conversation_id)
    if not template:
        raise HTTPException(status_code=404, detail="State table template not found")
    rows = await store.list_table_rows(conversation_id, template.template_id)
    return {
        "conversation_id": conversation_id,
        "template": _state_table_template_to_dict(template),
        "rows": [_state_table_row_to_dict(row) for row in rows],
    }


@router.post("/admin/conversations/{conversation_id}/state/tables/{table_key}/rows")
async def upsert_conversation_state_table_row(conversation_id: str, table_key: str, request: Request, data: dict = Body(...)):
    """Create or update one row in a table-based state board."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_schema import StateTableRow
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_conversation_table_template(conversation_id)
    if not template:
        raise HTTPException(status_code=404, detail="State table template not found")
    table = next((item for item in template.tables if item.table_key == table_key), None)
    if not table:
        raise HTTPException(status_code=404, detail="State table not found")
    values = data.get("values") if isinstance(data.get("values"), dict) else {}
    row = StateTableRow(
        row_id=data.get("row_id"),
        conversation_id=conversation_id,
        template_id=template.template_id or "",
        table_id=table.table_id or "",
        table_key=table.table_key,
        status=data.get("status", "active"),
        priority=int(data.get("priority", table.prompt_priority)),
        confidence=float(data.get("confidence", 0.9)),
        source="manual",
        metadata=data.get("metadata", {}),
    )
    row_id = await store.upsert_table_row(row, values)
    await store.record_table_event(
        conversation_id,
        "manual_upsert_row",
        table_key=table.table_key,
        row_id=row_id,
        after=values,
        reason=data.get("reason", "GUI manual edit"),
    )
    return {"status": "ok", "row_id": row_id}


@router.delete("/admin/state/table-rows/{row_id}")
async def delete_conversation_state_table_row(row_id: str, request: Request):
    """Resolve one row in a table-based state board."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    ok = await SQLiteStateStore(get_config().storage.sqlite.memory_db).update_table_row_status(row_id, "resolved", "GUI delete")
    return {"status": "ok" if ok else "error", "message": None if ok else "State table row not found"}


@router.get("/admin/conversations/{conversation_id}/state/events")
async def get_conversation_state_events(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List hot-state change events."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    events, total = await store.list_state_events(conversation_id, limit=limit, offset=offset)
    return {"items": events, "total": total, "limit": limit, "offset": offset}


@router.get("/admin/conversations/{conversation_id}/retrieval-decisions")
async def get_retrieval_decisions(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List Retrieval Gate decisions for debugging."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    decisions, total = await store.list_retrieval_decisions(conversation_id, limit=limit, offset=offset)
    return {"items": decisions, "total": total, "limit": limit, "offset": offset}


@router.post("/admin/conversations/{conversation_id}/state")
async def create_conversation_state_item(conversation_id: str, request: Request, data: dict = Body(...)):
    """Manually create or upsert a hot-state item."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_schema import ConversationStateItem
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    item_id = await store.upsert_item(ConversationStateItem(
        item_id=data.get("item_id"),
        template_id=data.get("template_id"),
        tab_id=data.get("tab_id"),
        field_id=data.get("field_id"),
        field_key=data.get("field_key"),
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
        world_id=data.get("world_id"),
        conversation_id=conversation_id,
        category=data.get("category", "scene"),
        item_key=data.get("item_key"),
        title=data.get("title"),
        content=data.get("item_value") or data.get("content", ""),
        status=data.get("status", "active"),
        priority=int(data.get("priority", 50)),
        user_locked=bool(data.get("user_locked", False)),
        confidence=float(data.get("confidence", 0.8)),
        source="manual",
        linked_card_ids=data.get("linked_card_ids", []),
        linked_summary_ids=data.get("linked_summary_ids", []),
        metadata=data.get("metadata", {}),
        expires_at=data.get("expires_at"),
    ))
    return {"status": "ok", "item_id": item_id}


@router.patch("/admin/state/{item_id}")
async def update_conversation_state_item(item_id: str, request: Request, data: dict = Body(...)):
    """Edit a hot-state item."""
    _require_admin(request)
    import json as json_mod
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    updates = dict(data)
    if "linked_card_ids" in updates:
        updates["linked_card_ids_json"] = json_mod.dumps(updates.pop("linked_card_ids"), ensure_ascii=False)
    if "linked_summary_ids" in updates:
        updates["linked_summary_ids_json"] = json_mod.dumps(updates.pop("linked_summary_ids"), ensure_ascii=False)
    if "metadata" in updates:
        updates["metadata_json"] = json_mod.dumps(updates.pop("metadata"), ensure_ascii=False)
    if "user_locked" in updates:
        updates["user_locked"] = 1 if updates["user_locked"] else 0
    if "item_value" in updates and "content" not in updates:
        updates["content"] = updates["item_value"]
    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    ok = await store.update_item(item_id, updates)
    return {"status": "ok" if ok else "error", "message": None if ok else "State item not found or no fields updated"}


@router.post("/admin/state/{item_id}/resolve")
async def resolve_conversation_state_item(item_id: str, request: Request, data: dict = Body(default={})):
    """Mark a hot-state item as resolved."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    await SQLiteStateStore(get_config().storage.sqlite.memory_db).resolve_item(item_id, data.get("reason"))
    return {"status": "ok"}


@router.delete("/admin/state/{item_id}")
async def delete_conversation_state_item(item_id: str, request: Request):
    """Permanently delete a hot-state item."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    await SQLiteStateStore(get_config().storage.sqlite.memory_db).hard_delete_item(item_id)
    return {"status": "ok"}


@router.get("/admin/conversations/{conversation_id}/state/preview")
async def preview_state_board(conversation_id: str, request: Request):
    """Return the rendered state board text as it would be injected into the LLM prompt."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_renderer import render_state_board
    from app.memory.state_schema import StateRenderOptions
    from app.memory.state_table_renderer import render_state_tables
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    store = SQLiteStateStore(cfg.storage.sqlite.memory_db)
    items = await store.list_active_items(conversation_id)
    template = await store.get_conversation_template(conversation_id)
    table_template = await store.get_conversation_table_template(conversation_id)
    table_rows = await store.list_table_rows(conversation_id, table_template.template_id if table_template else None)
    hot = cfg.memory.hot_context
    options = StateRenderOptions(
        max_chars=hot.max_chars,
        include_sections=hot.include_sections,
        section_order=hot.section_order,
        max_items_per_section=hot.max_items_per_section,
    )
    text = render_state_tables(table_template, table_rows, options, lang=cfg.language)
    if not text:
        text = render_state_board(
        items,
        options,
        template,
        lang=cfg.language,
    )
    return {
        "preview": text,
        "char_count": len(text),
        "max_chars": hot.max_chars,
        "item_count": len(table_rows) if table_rows else len(items),
    }


@router.post("/admin/conversations/{conversation_id}/state/rebuild")
async def rebuild_conversation_state(conversation_id: str, request: Request, data: dict = Body(default={})):
    """Rebuild hot-state by projecting approved boundary/preference cards."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_projector import project_cards_to_state

    cfg = get_config()
    result = await project_cards_to_state(
        cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
    )
    return {"status": "ok", **result}


@router.post("/admin/conversations/{conversation_id}/state/fill")
async def fill_conversation_state_once(conversation_id: str, request: Request, data: dict = Body(...)):
    """Manually run the model-driven state board filler."""
    _require_admin(request)
    from app.core.state import get_config
    from app.memory.state_filler import StateFillerConfigView, fill_conversation_state
    from app.memory.state_table_filler import fill_conversation_state_tables

    cfg = get_config()
    filler_config = StateFillerConfigView(
        provider=data.get("provider") or cfg.memory.state_updater.provider,
        base_url=data.get("base_url") or cfg.memory.state_updater.base_url or cfg.memory.judge.base_url or cfg.llm.base_url,
        api_key=data.get("api_key") or cfg.memory.state_updater.get_api_key() or cfg.memory.judge.get_api_key() or cfg.llm.get_api_key(),
        model=data.get("model") or cfg.memory.state_updater.model or cfg.memory.judge.model or cfg.llm.model,
        timeout_seconds=int(data.get("timeout_seconds") or cfg.memory.state_updater.timeout_seconds),
        temperature=float(data.get("temperature") if data.get("temperature") is not None else cfg.memory.state_updater.temperature),
        min_confidence=float(data.get("min_confidence") if data.get("min_confidence") is not None else cfg.memory.state_updater.min_confidence),
        prompt=data.get("prompt") or cfg.memory.state_updater.prompt,
    )
    table_result = await fill_conversation_state_tables(
        db_path=cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        user_message=data.get("user_message", ""),
        assistant_message=data.get("assistant_message", ""),
        config=filler_config,
        lang=cfg.language,
    )
    if table_result.applied > 0 or data.get("table_only", True):
        return {
            "status": "ok",
            "mode": "table",
            "applied": table_result.applied,
            "skipped": table_result.skipped,
            "operations": [operation.__dict__ for operation in table_result.operations],
            "notes": table_result.notes,
        }
    result = await fill_conversation_state(
        db_path=cfg.storage.sqlite.memory_db,
        conversation_id=conversation_id,
        user_id=data.get("user_id"),
        character_id=data.get("character_id"),
        user_message=data.get("user_message", ""),
        assistant_message=data.get("assistant_message", ""),
        config=filler_config,
        lang=cfg.language,
    )
    return {
        "status": "ok",
        "mode": "legacy",
        "applied": result.applied,
        "skipped": result.skipped,
        "updates": [update.__dict__ for update in result.updates],
        "notes": result.notes,
    }


@router.post("/admin/inbox/{inbox_id}/reject")
async def reject_inbox_item(inbox_id: str, data=Body(default="")):
    """Reject an inbox item."""
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

    claimed = await transition_inbox_status(db_path, inbox_id, "pending", "rejected", review_note=note)
    if not claimed:
        latest = await get_inbox_item(db_path, inbox_id)
        latest_status = latest["status"] if latest else "missing"
        return {"status": "error", "message": f"Item already {latest_status}"}
    await insert_review_action(db_path, action="reject", inbox_id=inbox_id, note=note)
    return {"status": "ok"}


# --- 状态板清空 API ---

@router.post("/admin/conversations/{conversation_id}/state/clear")
async def clear_conversation_state(conversation_id: str, request: Request):
    """Soft-delete all active state items for a conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    cleared = await store.clear_conversation_state_items(conversation_id)
    return {"status": "ok", "cleared": cleared}


@router.post("/admin/conversations/{conversation_id}/state/copy")
async def copy_conversation_state(conversation_id: str, request: Request, data: dict = Body(...)):
    """Copy state items and optionally mounts to a target conversation."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import copy_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    target_id = data.get("target_conversation_id")
    if not target_id:
        raise HTTPException(status_code=400, detail="target_conversation_id is required")
    if target_id == conversation_id:
        raise HTTPException(status_code=400, detail="target_conversation_id must differ from source")

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    store = SQLiteStateStore(db_path)
    copied_items = await store.copy_state_items(conversation_id, target_id)

    copied_mounts = 0
    if data.get("copy_mounts", True):
        copied_mounts = await copy_conversation_mounts(db_path, conversation_id, target_id)

    return {"status": "ok", "copied_items": copied_items, "copied_mounts": copied_mounts}


@router.post("/admin/conversations/{conversation_id}/state/reset")
async def reset_conversation_state(conversation_id: str, request: Request):
    """Clear state items but keep the template binding."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    cleared = await store.reset_to_template_empty(conversation_id)
    return {"status": "ok", "cleared": cleared}


@router.get("/admin/conversations/{conversation_id}/export")
async def export_conversation_state_bundle(conversation_id: str, request: Request):
    """Export a conversation state-board bundle: config, template snapshot, mounts, and state items."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    store = SQLiteStateStore(db_path)
    mounts = await get_conversation_mounts(db_path, conversation_id)
    mounted_library_ids = [mount["library_id"] for mount in mounts]
    write_library_id = next(
        (mount["library_id"] for mount in mounts if mount.get("is_write_target")),
        mounted_library_ids[0] if mounted_library_ids else "lib_default",
    )
    template = await store.get_conversation_template(conversation_id)
    state_items, total = await store.list_items(conversation_id, limit=5000)
    return {
        "format": "kokoromemo_conversation_state_v1",
        "conversation_id": conversation_id,
        "config": {
            "template_id": template.template_id if template else None,
            "mounted_library_ids": mounted_library_ids,
            "write_library_id": write_library_id,
        },
        "template": _template_to_dict(template) if template else None,
        "mounts": mounts,
        "state_items": [_state_item_to_dict(item) for item in state_items],
        "state_item_count": total,
    }


@router.post("/admin/conversations/import")
async def import_conversation_state_bundle(request: Request, data: dict = Body(...)):
    """Import a conversation state-board bundle into an existing or new conversation ID."""
    _require_admin(request)
    from app.core.ids import sanitize_id
    from app.core.state import get_config
    from app.memory.state_schema import ConversationStateItem
    from app.storage.sqlite_cards import set_conversation_mounts
    from app.storage.sqlite_state import SQLiteStateStore

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    source_conversation_id = data.get("conversation_id") or "imported"
    target_conversation_id = sanitize_id(
        data.get("target_conversation_id")
        or data.get("new_conversation_id")
        or source_conversation_id
    )
    overwrite_state = bool(data.get("overwrite_state", False))
    import_template_snapshot = bool(data.get("import_template_snapshot", True))
    config = data.get("config") or {}
    state_items = data.get("state_items") or []
    template_data = data.get("template")

    store = SQLiteStateStore(db_path)
    template_id = config.get("template_id")
    if import_template_snapshot and isinstance(template_data, dict):
        template_id = await store.save_template(_template_from_payload(_template_import_payload(template_data)))
    elif template_id and not await store.get_template(template_id):
        template_id = None

    if template_id:
        await store.set_conversation_template(target_conversation_id, template_id)

    library_ids = config.get("mounted_library_ids") or [mount.get("library_id") for mount in data.get("mounts", []) if mount.get("library_id")]
    if library_ids:
        await set_conversation_mounts(
            db_path,
            conversation_id=target_conversation_id,
            library_ids=library_ids,
            write_library_id=config.get("write_library_id"),
        )

    if overwrite_state:
        await store.clear_conversation_state_items(target_conversation_id)

    imported = 0
    for raw_item in state_items:
        if not isinstance(raw_item, dict):
            continue
        item = ConversationStateItem(
            item_id=None,
            conversation_id=target_conversation_id,
            category=raw_item.get("category", "scene"),
            content=raw_item.get("item_value") or raw_item.get("content", ""),
            template_id=template_id or raw_item.get("template_id"),
            tab_id=raw_item.get("tab_id"),
            field_id=raw_item.get("field_id"),
            field_key=raw_item.get("field_key"),
            user_id=raw_item.get("user_id"),
            character_id=raw_item.get("character_id"),
            world_id=raw_item.get("world_id"),
            item_key=raw_item.get("item_key"),
            title=raw_item.get("title"),
            confidence=float(raw_item.get("confidence", 0.7)),
            source="import",
            status=raw_item.get("status", "active"),
            priority=int(raw_item.get("priority", 0)),
            user_locked=bool(raw_item.get("user_locked", False)),
            source_turn_ids=raw_item.get("source_turn_ids") or [],
            source_message_ids=raw_item.get("source_message_ids") or [],
            linked_card_ids=raw_item.get("linked_card_ids") or [],
            linked_summary_ids=raw_item.get("linked_summary_ids") or [],
            metadata={**(raw_item.get("metadata") or {}), "imported_from": source_conversation_id},
            expires_at=raw_item.get("expires_at"),
        )
        await store.upsert_item(item)
        imported += 1

    return {
        "status": "ok",
        "conversation_id": target_conversation_id,
        "template_id": template_id,
        "imported_items": imported,
    }


# --- 记忆挂载预设 API ---

@router.get("/admin/memory-mount-presets")
async def list_memory_mount_presets_api():
    """List all active memory mount presets."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import list_mount_presets

    cfg = get_config()
    items = await list_mount_presets(cfg.storage.sqlite.memory_db)
    return {"items": items}


@router.post("/admin/memory-mount-presets")
async def create_memory_mount_preset_api(data: dict = Body(...)):
    """Create a new memory mount preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_mount_preset

    cfg = get_config()
    preset_id = await create_mount_preset(
        cfg.storage.sqlite.memory_db,
        name=data.get("name") or "未命名挂载组合",
        library_ids=data.get("library_ids") or [],
        write_library_id=data.get("write_library_id") or "",
        description=data.get("description", ""),
    )
    return {"status": "ok", "preset_id": preset_id}


@router.put("/admin/memory-mount-presets/{preset_id}")
async def update_memory_mount_preset_api(preset_id: str, data: dict = Body(...)):
    """Update a memory mount preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import update_mount_preset

    cfg = get_config()
    ok = await update_mount_preset(
        cfg.storage.sqlite.memory_db,
        preset_id=preset_id,
        name=data.get("name"),
        description=data.get("description"),
        library_ids=data.get("library_ids"),
        write_library_id=data.get("write_library_id"),
    )
    return {"status": "ok" if ok else "error", "message": None if ok else "预设不存在"}


@router.delete("/admin/memory-mount-presets/{preset_id}")
async def delete_memory_mount_preset_api(preset_id: str):
    """Delete a memory mount preset."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import delete_mount_preset

    cfg = get_config()
    ok = await delete_mount_preset(cfg.storage.sqlite.memory_db, preset_id)
    return {"status": "ok" if ok else "error", "message": None if ok else "预设不存在"}


# --- 导入 / 导出 API ---

@router.get("/admin/memory-libraries/{library_id}/export")
async def export_memory_library(library_id: str):
    """Export a memory library with all its cards as JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import init_cards_db
    import aiosqlite

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    await init_cards_db(db_path)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        lib_cursor = await db.execute(
            "SELECT * FROM memory_libraries WHERE library_id = ?", (library_id,)
        )
        lib_row = await lib_cursor.fetchone()
        if not lib_row:
            raise HTTPException(status_code=404, detail="记忆库不存在")

        cards_cursor = await db.execute(
            """SELECT * FROM memory_cards WHERE library_id = ? AND status != 'deleted'
               ORDER BY created_at ASC""",
            (library_id,),
        )
        cards = [dict(r) for r in await cards_cursor.fetchall()]

    lib = dict(lib_row)
    return {
        "format": "kokoromemo_library_v1",
        "library": {
            "library_id": lib["library_id"],
            "name": lib["name"],
            "description": lib["description"],
            "is_builtin": lib["is_builtin"],
        },
        "cards": cards,
    }


@router.post("/admin/memory-libraries/import")
async def import_memory_library(data: dict = Body(...)):
    """Import a memory library from exported JSON."""
    from app.core.ids import generate_id
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_memory_library, insert_card, insert_card_version

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db

    library_data = data.get("library", {})
    new_library_id = await create_memory_library(
        db_path,
        name=library_data.get("name") or "导入的记忆库",
        description=library_data.get("description", ""),
    )

    imported = 0
    for card in data.get("cards", []):
        card_id = generate_id("card_")
        await insert_card(
            db_path,
            card_id=card_id,
            library_id=new_library_id,
            user_id=card.get("user_id", "default_user"),
            character_id=card.get("character_id"),
            conversation_id=card.get("conversation_id"),
            scope=card.get("scope", "global"),
            card_type=card.get("card_type", "preference"),
            content=card.get("content", ""),
            title=card.get("title"),
            summary=card.get("summary"),
            importance=float(card.get("importance", 0.5)),
            confidence=float(card.get("confidence", 0.7)),
            status=card.get("status", "approved"),
            is_pinned=int(card.get("is_pinned", 0)),
            evidence_text=card.get("evidence_text"),
        )
        imported += 1

    return {"status": "ok", "library_id": new_library_id, "imported_cards": imported}


@router.get("/admin/state/templates/{template_id}/export")
async def export_state_template(template_id: str):
    """Export a state board template with tabs and fields as JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template = await store.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    return {
        "format": "kokoromemo_template_v1",
        "template": _template_to_dict(template),
    }


@router.post("/admin/state/templates/import")
async def import_state_template(data: dict = Body(...)):
    """Import a state board template from exported JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_state import SQLiteStateStore

    template_data = data.get("template", data)

    store = SQLiteStateStore(get_config().storage.sqlite.memory_db)
    template_id = await store.save_template(_template_from_payload(_template_import_payload(template_data)))
    return {"status": "ok", "template_id": template_id}


@router.get("/admin/memory-mount-presets/{preset_id}/export")
async def export_mount_preset(preset_id: str):
    """Export a memory mount preset as JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import get_mount_preset

    cfg = get_config()
    preset = await get_mount_preset(cfg.storage.sqlite.memory_db, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    return {
        "format": "kokoromemo_mount_preset_v1",
        "preset": {
            "name": preset["name"],
            "description": preset["description"],
            "library_ids_json": preset["library_ids_json"],
            "write_library_id": preset["write_library_id"],
        },
    }


@router.post("/admin/memory-mount-presets/import")
async def import_mount_preset(data: dict = Body(...)):
    """Import a memory mount preset from exported JSON."""
    from app.core.state import get_config
    from app.storage.sqlite_cards import create_mount_preset
    import json as json_mod

    preset_data = data.get("preset", data)
    library_ids = json_mod.loads(preset_data.get("library_ids_json", "[]"))

    cfg = get_config()
    preset_id = await create_mount_preset(
        cfg.storage.sqlite.memory_db,
        name=preset_data.get("name") or "导入的挂载组合",
        library_ids=library_ids,
        write_library_id=preset_data.get("write_library_id") or (library_ids[0] if library_ids else "lib_default"),
        description=preset_data.get("description", ""),
    )
    return {"status": "ok", "preset_id": preset_id}


# --- 会话导入 / 导出 ---


@router.get("/admin/memory-graph")
async def get_memory_graph(
    request: Request,
    library_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
):
    """Return graph data (nodes + edges) for visualization."""
    _require_admin(request)
    import aiosqlite
    from app.core.state import get_config

    cfg = get_config()
    db_path = cfg.storage.sqlite.memory_db
    nodes = []
    edges = []

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT card_id, card_type, content, importance, confidence, scope FROM memory_cards WHERE status = 'approved'"
            params: list = []
            if library_id:
                query += " AND library_id = ?"
                params.append(library_id)
            query += " ORDER BY importance DESC LIMIT ?"
            params.append(limit)

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            card_ids = set()
            for row in rows:
                card_ids.add(row["card_id"])
                nodes.append({
                    "id": row["card_id"],
                    "label": row["content"][:60],
                    "type": row["card_type"],
                    "importance": row["importance"],
                    "confidence": row["confidence"],
                    "scope": row["scope"],
                })

            if card_ids:
                placeholders = ",".join("?" * len(card_ids))
                cursor = await db.execute(
                    f"SELECT source_card_id, target_card_id, edge_type, weight, confidence "
                    f"FROM memory_edges WHERE status = 'active' "
                    f"AND (source_card_id IN ({placeholders}) OR target_card_id IN ({placeholders}))",
                    list(card_ids) + list(card_ids),
                )
                for row in await cursor.fetchall():
                    edges.append({
                        "source": row["source_card_id"],
                        "target": row["target_card_id"],
                        "type": row["edge_type"],
                        "weight": row["weight"],
                        "confidence": row["confidence"],
                    })
    except Exception:
        pass

    return {"nodes": nodes, "edges": edges}


@router.post("/admin/import/sillytavern")
async def import_sillytavern(request: Request, data: dict = Body(...)):
    """Import a SillyTavern JSONL chat log."""
    _require_admin(request)
    from app.core.ids import generate_id
    from app.core.state import get_config
    from app.importers.sillytavern import parse_sillytavern_jsonl
    from app.storage.sqlite_app import init_app_db, upsert_conversation
    from app.storage.sqlite_conversation import init_chat_db, save_turn_and_messages

    cfg = get_config()
    text = data.get("content", "")
    if not text:
        raise HTTPException(status_code=400, detail="content is required (JSONL text)")

    conv = parse_sillytavern_jsonl(text)
    if not conv.turns:
        return {"status": "error", "message": "No valid turns found in input"}

    user_id = data.get("user_id", "default")
    character_id = data.get("character_id") or None
    conversation_id = data.get("conversation_id") or generate_id("conv_import_")

    from pathlib import Path
    conv_dir = str(Path(cfg.storage.root_dir, "conversations", conversation_id))
    chat_db_path = str(Path(conv_dir, "chat.sqlite"))

    await init_app_db(cfg.storage.sqlite.app_db)
    await init_chat_db(chat_db_path)
    await upsert_conversation(
        cfg.storage.sqlite.app_db, conversation_id,
        user_id, character_id, "sillytavern_import", conv_dir,
    )

    messages = []
    if conv.system_prompt:
        messages.append({"role": "system", "content": conv.system_prompt})
    for turn in conv.turns:
        messages.append({"role": turn.role, "content": turn.content})

    turn_id = generate_id("turn_")
    request_id = generate_id("req_import_")
    await save_turn_and_messages(
        chat_db_path, turn_id, conversation_id, user_id, character_id, request_id, 0, messages,
    )

    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "turns_imported": len(conv.turns),
        "character_name": conv.character_name,
    }


@router.post("/admin/import/{conversation_id}/extract-memories")
async def extract_memories_from_import(conversation_id: str, request: Request, data: dict = Body(default={})):
    """Batch-extract memories from an imported conversation."""
    _require_admin(request)
    from app.core.services import get_embedding_provider, get_lancedb_store
    from app.core.state import get_config
    from app.memory.card_extractor import extract_and_route
    from app.memory.judge import MemoryJudgeConfigView
    from app.storage.sqlite_conversation import get_all_messages

    cfg = get_config()
    from pathlib import Path
    chat_db_path = str(Path(cfg.storage.root_dir, "conversations", conversation_id, "chat.sqlite"))

    if not Path(chat_db_path).exists():
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await get_all_messages(chat_db_path, conversation_id)
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(messages) - 1:
        if messages[i].get("role") == "user" and messages[i + 1].get("role") == "assistant":
            pairs.append((messages[i]["content"], messages[i + 1]["content"]))
            i += 2
        else:
            i += 1

    if not pairs:
        return {"status": "ok", "extracted_pairs": 0, "message": "No user-assistant pairs found"}

    user_id = data.get("user_id", "default")
    character_id = data.get("character_id") or None
    ep = get_embedding_provider(cfg)
    store = get_lancedb_store(cfg)

    judge_config = None
    if cfg.memory.judge.enabled and cfg.memory.judge.model:
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

    max_pairs = data.get("max_pairs", 50)
    extracted_count = 0
    for user_msg, assistant_msg in pairs[:max_pairs]:
        try:
            await extract_and_route(
                db_path=cfg.storage.sqlite.memory_db,
                user_message=user_msg,
                assistant_message=assistant_msg,
                user_id=user_id,
                character_id=character_id,
                conversation_id=conversation_id,
                embedding_provider=ep,
                lancedb_store=store,
                judge_config=judge_config,
                lang=cfg.language,
            )
            extracted_count += 1
        except Exception:
            continue

    return {"status": "ok", "extracted_pairs": extracted_count, "total_pairs": len(pairs)}
