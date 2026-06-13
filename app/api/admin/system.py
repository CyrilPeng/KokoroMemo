"""System routes: health, logs, stats, config, connectivity, update manifest."""

from __future__ import annotations

from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, Body, Query, Request

from app.api.admin._helpers import _require_admin

router = APIRouter()

_UPDATE_MANIFEST_SOURCES = [
    ("GitHub", "https://github.com/CyrilPeng/KokoroMemo/releases/latest/download/latest.json"),
    (
        "GitHub Proxy",
        "https://gh-proxy.org/https://github.com/CyrilPeng/KokoroMemo/releases/latest/download/latest.json",
    ),
]
_GITEE_LATEST_RELEASE_API = "https://gitee.com/api/v5/repos/CyrilPeng/KokoroMemo/releases/latest"


async def _fetch_update_json(client: httpx.AsyncClient, url: str) -> dict:
    resp = await client.get(url, headers={"Accept": "application/json"})
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:120]}")
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("返回内容不是 JSON 对象")
    return data


async def _fetch_gitee_update_manifest(client: httpx.AsyncClient) -> dict:
    release = await _fetch_update_json(client, _GITEE_LATEST_RELEASE_API)
    tag = release.get("tag_name") or release.get("name")
    attachments = (
        release.get("attach_files") if isinstance(release.get("attach_files"), list) else release.get("assets")
    )
    if not isinstance(attachments, list):
        attachments = []
    manifest_asset = next(
        (item for item in attachments if (item.get("name") or item.get("filename")) == "latest.json"), None
    )
    manifest_url = ""
    if manifest_asset:
        manifest_url = (
            manifest_asset.get("browser_download_url")
            or manifest_asset.get("download_url")
            or manifest_asset.get("url")
            or manifest_asset.get("html_url")
            or ""
        )
    if not manifest_url and tag:
        manifest_url = f"https://gitee.com/CyrilPeng/KokoroMemo/releases/download/{tag}/latest.json"
    if not manifest_url:
        raise RuntimeError("未找到 latest.json")
    return await _fetch_update_json(client, manifest_url)


@router.get("/admin/update-manifest")
async def get_update_manifest_api(request: Request):
    """按 GitHub、GitHub 代理、Gitee 顺序获取更新清单，避免浏览器跨域失败。"""
    _require_admin(request)
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        for source_name, url in _UPDATE_MANIFEST_SOURCES:
            try:
                data = await _fetch_update_json(client, url)
                return {"status": "ok", "sourceName": source_name, "data": data, "errors": errors}
            except Exception as exc:
                errors.append(f"{source_name}: {exc}")
        try:
            data = await _fetch_gitee_update_manifest(client)
            return {"status": "ok", "sourceName": "Gitee", "data": data, "errors": errors}
        except Exception as exc:
            errors.append(f"Gitee: {exc}")
    return {"status": "error", "message": "；".join(errors) or "无法获取更新清单", "errors": errors}


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


@router.get("/admin/logs")
async def read_server_logs(request: Request, lines: int = Query(default=200, ge=1, le=2000)):
    """读取后端日志末尾内容，方便移动端和 Termux 排查问题。"""
    _require_admin(request)
    from app.core.state import get_config

    cfg = get_config()
    candidates = [
        Path(cfg.storage.root_dir).parent / "logs" / "server.log",
        Path.cwd() / "logs" / "server.log",
        Path.cwd() / "server.log",
    ]
    log_path = next((path for path in candidates if path.exists()), None)
    if not log_path:
        return {
            "status": "missing",
            "path": str(candidates[0]),
            "content": "",
            "message": "未找到 server.log，请确认后端启动脚本是否把输出写入日志文件。",
        }
    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "status": "ok",
        "path": str(log_path),
        "line_count": len(content),
        "content": "\n".join(content[-lines:]),
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

            cursor = await db.execute("SELECT COUNT(*) FROM memory_inbox WHERE status IN ('discarded', 'rejected')")
            row = await cursor.fetchone()
            result["inbox_discarded"] = row[0] if row else 0

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
        result.setdefault("inbox_discarded", 0)

    return result


def _build_config_status(cfg) -> dict:
    def _check(base_url: str, api_key: str, model: str, *, enabled: bool = True) -> dict:
        if not enabled:
            return {"configured": False, "required": False, "reason": "disabled", "missing": []}
        missing = []
        if not base_url:
            missing.append("base_url")
        if not api_key:
            missing.append("api_key")
        if not model:
            missing.append("model")
        return {"configured": len(missing) == 0, "required": True, "missing": missing}

    llm_s = _check(cfg.llm.base_url, cfg.llm.get_api_key(), cfg.llm.model)
    emb_s = _check(
        cfg.embedding.base_url,
        cfg.embedding.get_api_key(),
        cfg.embedding.model,
        enabled=cfg.embedding.enabled,
    )
    rer_s = _check(
        cfg.rerank.base_url,
        cfg.rerank.get_api_key(),
        cfg.rerank.model,
        enabled=cfg.rerank.enabled,
    )
    rer_s["required"] = False

    judge_s = _check(
        cfg.memory.judge.base_url,
        cfg.memory.judge.get_api_key(),
        cfg.memory.judge.model,
        enabled=cfg.memory.judge.enabled and cfg.memory.extraction_enabled,
    )
    judge_s["required"] = cfg.memory.extraction_enabled

    sf_s = _check(
        cfg.memory.state_updater.base_url,
        cfg.memory.state_updater.get_api_key(),
        cfg.memory.state_updater.model,
        enabled=cfg.memory.state_updater.enabled,
    )
    sf_s["required"] = False

    required_list = [s for s in [llm_s, emb_s, judge_s] if s["required"]]
    ok_count = sum(1 for s in required_list if s["configured"])
    score = int((ok_count / max(len(required_list), 1)) * 100)

    return {
        "status": "ok",
        "health_score": score,
        "components": {
            "llm": {"name": "Chat LLM", "required": True, **llm_s},
            "embedding": {"name": "Embedding", "required": cfg.embedding.enabled, **emb_s},
            "rerank": {"name": "Rerank", "required": False, **rer_s},
            "judge": {"name": "Memory Judge", "required": judge_s["required"], **judge_s},
            "state_filler": {"name": "State Filler", "required": False, **sf_s},
        },
    }


async def _count_memory_first_run_signals(db_path: str) -> dict[str, int]:
    import aiosqlite

    result = {"approved": 0, "pending": 0, "candidate_chain": 0}
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM memory_cards WHERE status = 'approved'")
            row = await cursor.fetchone()
            result["approved"] = int(row[0] if row else 0)

            cursor = await db.execute("SELECT COUNT(*) FROM memory_inbox WHERE status = 'pending'")
            row = await cursor.fetchone()
            result["pending"] = int(row[0] if row else 0)
    except Exception:  # noqa: S110
        pass
    result["candidate_chain"] = result["pending"] + result["approved"]
    return result


async def _count_active_state_rows(db_path: str, conversation_id: str | None) -> int:
    if not conversation_id:
        return 0
    import aiosqlite

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM state_table_rows WHERE conversation_id = ? AND status = 'active'",
                (conversation_id,),
            )
            row = await cursor.fetchone()
            return int(row[0] if row else 0)
    except Exception:  # noqa: S110
        return 0


def _airp_step(
    key: str,
    done: bool,
    *,
    target: str | None,
    action_key: str | None,
    count: int = 0,
    optional: bool = False,
    command: str | None = None,
) -> dict:
    data = {
        "key": key,
        "done": done,
        "optional": optional,
        "target": target,
        "action_key": action_key,
        "count": count,
    }
    if command:
        data["command"] = command
    return data


@router.get("/admin/airp-first-run-status")
async def get_airp_first_run_status(request: Request):
    """Return the official first-run AIRP acceptance status for dashboard and clients."""
    _require_admin(request)
    from app.core.state import get_config
    from app.storage.sqlite_app import list_characters, list_conversations

    cfg = get_config()
    config_status = _build_config_status(cfg)
    config_ready = int(config_status.get("health_score") or 0) >= 100

    characters: list[dict] = []
    conversations: list[dict] = []
    active_conversation_total = 0
    try:
        characters = await list_characters(cfg.storage.sqlite.app_db)
        conversations, active_conversation_total = await list_conversations(
            cfg.storage.sqlite.app_db,
            limit=5,
            offset=0,
            status="active",
        )
    except Exception:  # noqa: S110
        pass

    role_ids = {item.get("character_id") for item in characters if item.get("character_id")}
    role_ids.update(item.get("character_id") for item in conversations if item.get("character_id"))
    role_count = len(role_ids)

    latest_conversation = conversations[0] if conversations else None
    latest_conversation_id = latest_conversation.get("conversation_id") if latest_conversation else None
    memory_counts = await _count_memory_first_run_signals(cfg.storage.sqlite.memory_db)
    state_row_count = await _count_active_state_rows(cfg.storage.sqlite.memory_db, latest_conversation_id)

    conversation_ready = active_conversation_total > 0
    role_ready = role_count > 0
    candidate_ready = memory_counts["candidate_chain"] > 0
    approved_ready = memory_counts["approved"] > 0
    state_ready = state_row_count > 0

    steps = [
        _airp_step(
            "config",
            config_ready,
            target="/settings",
            action_key="openSettings",
            count=int(config_status.get("health_score") or 0),
        ),
        _airp_step("role", role_ready, target="/characters", action_key="openRoles", count=role_count),
        _airp_step(
            "conversation",
            conversation_ready,
            target="/conversations" if conversation_ready else "/settings",
            action_key="openConversations" if conversation_ready else "openSettings",
            count=active_conversation_total,
        ),
        _airp_step(
            "candidate",
            candidate_ready,
            target="/inbox",
            action_key="openInbox",
            count=memory_counts["candidate_chain"],
        ),
        _airp_step(
            "approved",
            approved_ready,
            target="/inbox" if memory_counts["pending"] > 0 else "/memories",
            action_key="openInbox" if memory_counts["pending"] > 0 else "openMemories",
            count=memory_counts["approved"],
        ),
        _airp_step("state", state_ready, target="/state", action_key="openState", count=state_row_count),
    ]
    required_steps = [step for step in steps if not step["optional"]]
    ready_count = sum(1 for step in required_steps if step["done"])
    ready = ready_count == len(required_steps)
    steps.append(
        _airp_step(
            "benchmark",
            ready,
            target=None,
            action_key=None,
            optional=True,
            command="python benchmarks/run_airp_benchmark.py --smoke --report-dir benchmarks/reports/first-run",
        )
    )
    next_step = next((step for step in required_steps if not step["done"]), None)
    total = len(required_steps) or 1

    return {
        "status": "ok",
        "ready": ready,
        "progress": {
            "done": ready_count,
            "total": len(required_steps),
            "percentage": round((ready_count / total) * 100),
        },
        "steps": steps,
        "next_step": next_step,
        "summary": {
            "config_health_score": config_status.get("health_score", 0),
            "role_count": role_count,
            "active_conversation_count": active_conversation_total,
            "latest_conversation_id": latest_conversation_id,
            "pending_memory_count": memory_counts["pending"],
            "approved_memory_count": memory_counts["approved"],
            "state_row_count": state_row_count,
        },
    }


@router.get("/admin/config-status")
async def get_config_status(request: Request):
    """Return configuration completeness and readiness for dashboard."""
    _require_admin(request)
    from app.core.state import get_config

    return _build_config_status(get_config())


@router.get("/admin/action-items")
async def get_action_items(request: Request):
    """返回需要用户关注的待处理项计数。"""
    _require_admin(request)
    import aiosqlite

    from app.core.state import get_config

    cfg = get_config()
    items = []

    try:
        async with aiosqlite.connect(cfg.storage.sqlite.memory_db) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM memory_inbox WHERE status='pending'")
            row = await cursor.fetchone()
            inbox_pending = row[0] if row else 0
            if inbox_pending > 0:
                items.append(
                    {
                        "key": "inbox_pending",
                        "label": "待审核记忆",
                        "count": inbox_pending,
                        "severity": "warning",
                        "action": "navigate",
                        "target": "/inbox",
                    }
                )

            cursor = await db.execute("SELECT COUNT(*) FROM memory_cards WHERE status='approved' AND vector_synced=0")
            row = await cursor.fetchone()
            sync_failed = row[0] if row else 0
            if sync_failed > 0:
                items.append(
                    {
                        "key": "vector_sync_failed",
                        "label": "向量同步失败",
                        "count": sync_failed,
                        "severity": "error",
                        "action": "navigate",
                        "target": "/settings",
                    }
                )
    except Exception:  # noqa: S110
        pass

    return {"status": "ok", "items": items}


async def _chat_test(
    base_url: str, api_key: str, model: str, provider: str = "openai_compatible", timeout: int = 15
) -> dict:
    """通用 chat completion 测试（适用于 llm、judge、state_filler）。"""
    import time

    base_url = base_url.rstrip("/")
    if not base_url or not api_key or not model:
        return {"status": "skipped", "latency_ms": 0, "message": "未配置 base_url / api_key / model"}

    is_gemini = provider == "gemini" or "googleapis.com" in base_url
    is_anthropic = provider == "anthropic" or "anthropic.com" in base_url

    if is_gemini:
        url = f"{base_url}/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        body = {"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 1}}
    elif is_anthropic:
        url = f"{base_url}/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        body = {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
    else:
        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {"model": model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            latency = int((time.monotonic() - t0) * 1000)
            if resp.status_code == 200:
                return {"status": "ok", "latency_ms": latency, "message": ""}
            return {"status": "error", "latency_ms": latency, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.TimeoutException:
        latency = int((time.monotonic() - t0) * 1000)
        return {"status": "error", "latency_ms": latency, "message": "连接超时，请检查 Base URL 和网络"}
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"status": "error", "latency_ms": latency, "message": str(e)[:200]}


async def _embedding_test(base_url: str, api_key: str, model: str, timeout: int = 10) -> dict:
    """Embedding 模型测试。"""
    import time

    base_url = base_url.rstrip("/")
    if not base_url or not api_key or not model:
        return {"status": "skipped", "latency_ms": 0, "message": "未配置 base_url / api_key / model"}

    url = f"{base_url}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "input": "test"}

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            latency = int((time.monotonic() - t0) * 1000)
            if resp.status_code == 200:
                return {"status": "ok", "latency_ms": latency, "message": ""}
            return {"status": "error", "latency_ms": latency, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.TimeoutException:
        latency = int((time.monotonic() - t0) * 1000)
        return {"status": "error", "latency_ms": latency, "message": "连接超时"}
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"status": "error", "latency_ms": latency, "message": str(e)[:200]}


async def _rerank_test(base_url: str, api_key: str, model: str, timeout: int = 10) -> dict:
    """Rerank 模型测试。"""
    import time

    base_url = base_url.rstrip("/")
    if not base_url or not api_key or not model:
        return {"status": "skipped", "latency_ms": 0, "message": "未配置 base_url / api_key / model"}

    url = f"{base_url}/rerank"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model, "query": "test", "documents": ["a", "b"]}

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body, headers=headers)
            latency = int((time.monotonic() - t0) * 1000)
            if resp.status_code == 200:
                return {"status": "ok", "latency_ms": latency, "message": ""}
            return {"status": "error", "latency_ms": latency, "message": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.TimeoutException:
        latency = int((time.monotonic() - t0) * 1000)
        return {"status": "error", "latency_ms": latency, "message": "连接超时"}
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"status": "error", "latency_ms": latency, "message": str(e)[:200]}


async def _test_one_provider(cfg, target: str) -> dict:
    """对单个 provider 发起最小请求并返回结果。"""
    if target == "llm":
        return await _chat_test(
            cfg.llm.base_url, cfg.llm.get_api_key(), cfg.llm.model, cfg.llm.provider, cfg.llm.timeout_seconds
        )
    elif target == "embedding":
        if not cfg.embedding.enabled:
            return {"status": "skipped", "latency_ms": 0, "message": "Embedding 已禁用"}
        return await _embedding_test(
            cfg.embedding.base_url, cfg.embedding.get_api_key(), cfg.embedding.model, cfg.embedding.timeout_seconds
        )
    elif target == "rerank":
        if not cfg.rerank.enabled:
            return {"status": "skipped", "latency_ms": 0, "message": "Rerank 已禁用"}
        return await _rerank_test(
            cfg.rerank.base_url, cfg.rerank.get_api_key(), cfg.rerank.model, cfg.rerank.timeout_seconds
        )
    elif target == "judge":
        if not cfg.memory.judge.enabled:
            return {"status": "skipped", "latency_ms": 0, "message": "记忆判断未启用"}
        return await _chat_test(
            cfg.memory.judge.base_url,
            cfg.memory.judge.get_api_key(),
            cfg.memory.judge.model,
            cfg.memory.judge.provider,
            cfg.memory.judge.timeout_seconds,
        )
    elif target == "state_filler":
        if not cfg.memory.state_updater.enabled:
            return {"status": "skipped", "latency_ms": 0, "message": "状态板填充未启用"}
        return await _chat_test(
            cfg.memory.state_updater.base_url,
            cfg.memory.state_updater.get_api_key(),
            cfg.memory.state_updater.model,
            cfg.memory.state_updater.provider,
            cfg.memory.state_updater.timeout_seconds,
        )
    else:
        return {"status": "error", "latency_ms": 0, "message": f"未知 target: {target}"}


@router.post("/admin/connectivity-test")
async def test_connectivity(data: dict = Body(...), request: Request = None):
    """测试指定模型 provider 的真实连通性。"""
    _require_admin(request)
    from app.core.state import get_config

    cfg = get_config()
    target = data.get("target", "all")
    targets = ["llm", "embedding", "rerank", "judge", "state_filler"] if target == "all" else [target]

    results = {}
    for t in targets:
        results[t] = await _test_one_provider(cfg, t)
    return {"status": "ok", "results": results}


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
            "api_key": "",
            "api_key_set": bool(embedding_key),
            "model": cfg.embedding.model,
            "dimension": cfg.embedding.dimension,
        },
        "rerank": {
            "enabled": cfg.rerank.enabled,
            "provider": cfg.rerank.provider,
            "base_url": cfg.rerank.base_url,
            "api_key": "",
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
                "api_key": "",
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
                "update_after_each_turn": cfg.memory.state_updater.update_after_each_turn,
                "update_every_n_turns": cfg.memory.state_updater.update_every_n_turns,
                "min_confidence": cfg.memory.state_updater.min_confidence,
                "provider": cfg.memory.state_updater.provider,
                "base_url": cfg.memory.state_updater.base_url,
                "api_key": "",
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
            "api_key": "",
            "api_key_set": bool(llm_key),
            "model": cfg.llm.model,
        },
        "conversation": {
            "session_identity_mode": cfg.conversation.session_identity_mode,
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
        with open(config_path, encoding="utf-8") as f:
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
                    suffix = val[len(default_prefix) :]
                    sqlite[key] = str(Path(new_root) / suffix)
            lancedb = storage.get("lancedb", {})
            ldb_val = lancedb.get("path", "")
            if ldb_val.startswith(default_prefix):
                suffix = ldb_val[len(default_prefix) :]
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
    needs_restart = new_cfg.storage.root_dir != old_root_dir or new_cfg.server.port != old_port

    if needs_restart:
        import logging

        logger = logging.getLogger("kokoromemo")
        logger.info("配置变更需要重启服务（存储目录或端口已更改）")
        return {"status": "restart_required", "message": "配置已保存，正在重启服务..."}

    return {"status": "ok", "message": "配置已保存并生效"}
