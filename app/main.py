"""KokoroMemo - Local long-term memory proxy for AI role-playing."""

from __future__ import annotations

import os
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from app.core.config import load_config, resolve_config_path
from app.core.lifecycle import AppLifecycle
from app.core.logging import setup_logging
from app.core.state import set_config
from app.core.time_util import set_configured_timezone


def _read_version() -> str:
    """从 pyproject.toml 读取版本号，作为版本单一来源。"""
    env_version = os.getenv("KOKOROMEMO_VERSION")
    if env_version:
        return env_version

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    if pyproject.exists():
        with open(pyproject, encoding="utf-8") as f:
            data = tomllib.loads(f.read())
            return data.get("project", {}).get("version", "0.0.0")

    try:
        from importlib.metadata import version as _get_version

        return _get_version("kokoromemo")
    except Exception:  # noqa: S110
        pass

    try:
        from kokoromemo._version import __version__

        return __version__
    except Exception:
        return "0.0.0"


def _android_compat_enabled() -> bool:
    return os.getenv("KOKOROMEMO_ANDROID_COMPAT", "0").lower() in {"1", "true", "yes"}


# 回退端口选择范围：当用户配置的首选端口不可用时，从此范围中随机选择
_FALLBACK_PORT_MIN = 20000
_FALLBACK_PORT_MAX = 40000
_FALLBACK_PORT_RETRIES = 50

# 静态资源缓存 TTL（秒）：打包产物使用不可变长缓存，HTML 使用不缓存
_STATIC_ASSET_MAX_AGE = 365 * 24 * 3600  # 1 年（打包资源带 content hash）
_HTML_MAX_AGE = 3600  # 1 小时（SPA 入口页不缓存，保证新版本即时生效）


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    cfg = load_config()
    set_config(cfg)
    set_configured_timezone(cfg.server.timezone or None)
    setup_logging(cfg.server.log_level)

    lifecycle = AppLifecycle(app, cfg)
    await lifecycle.start()
    app.state.lifecycle = lifecycle
    import logging

    logger = logging.getLogger("kokoromemo")
    logger.info("KokoroMemo started on %s:%d", cfg.server.host, cfg.server.port)

    # 安全提醒：未配置管理令牌时绑定非回环地址存在风险。
    if cfg.server.host not in {"127.0.0.1", "localhost", "::1"} and not cfg.server.get_admin_token():
        logger.warning(
            "Server bound to %s without an admin_token; admin endpoints will refuse remote "
            "requests unless server.allow_remote_access is true. Set ADMIN_TOKEN or "
            "admin_token in config to enable secure remote access.",
            cfg.server.host,
        )

    yield

    logger.info("KokoroMemo shutting down")
    await lifecycle.stop()


def create_app() -> FastAPI:
    """Create and fully configure the FastAPI application.

    The entire app (routing, middleware, static serving) is constructed in
    this single factory call, eliminating the previous split between a
    bare `FastAPI(...)` instance and a separate `create_app()` invocation
    at import time. This avoids redundant config loads and makes the
    module safe to import without side effects beyond app creation.
    """
    from app.api.routes_admin import router as admin_router
    from app.api.routes_anthropic import router as anthropic_router
    from app.api.routes_gemini import router as gemini_router
    from app.api.routes_openai import router as openai_router
    from app.api.routes_responses import router as responses_router
    from app.api.routes_ws import router as ws_router

    application = FastAPI(title="KokoroMemo", version=_read_version(), lifespan=lifespan)
    application.state.app_version = application.version
    application.state.actual_port = None

    application.include_router(admin_router)
    application.include_router(anthropic_router)
    application.include_router(gemini_router)
    application.include_router(openai_router)
    application.include_router(responses_router)
    application.include_router(ws_router)

    if not _android_compat_enabled():
        application.add_middleware(GZipMiddleware, minimum_size=1024)

    class CacheStaticFiles(StaticFiles):
        def file_response(self, *args, **kwargs) -> Response:
            response = super().file_response(*args, **kwargs)
            response.headers.setdefault("Cache-Control", f"public, max-age={_STATIC_ASSET_MAX_AGE}, immutable")
            return response

    # 如果存在预构建前端，则提供 Vue SPA 静态资源（Web UI / Termux 模式）。
    _web_dist_env = os.getenv("KOKOROMEMO_WEB_DIST", "").strip()
    _gui_dist = (
        Path(_web_dist_env).expanduser() if _web_dist_env else Path(__file__).resolve().parent.parent / "gui" / "dist"
    )
    if _gui_dist.is_dir():
        application.mount("/assets", CacheStaticFiles(directory=_gui_dist / "assets"), name="static-assets")

        _API_PREFIXES = ("/admin", "/v1", "/v1beta", "/anthropic", "/responses", "/health", "/ws")

        @application.get("/.port")
        async def serve_actual_port():
            actual_port = getattr(application.state, "actual_port", None) or os.getenv("KOKOROMEMO_ACTUAL_PORT")
            return Response(str(actual_port or ""), media_type="text/plain")

        @application.get("/{path:path}")
        async def serve_spa(path: str):
            # 让 API 路由自行处理所属路径
            if any(path.startswith(p.lstrip("/")) for p in _API_PREFIXES):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            file = _gui_dist / path
            if file.is_file():
                response = FileResponse(file)
                response.headers.setdefault("Cache-Control", f"public, max-age={_HTML_MAX_AGE}")
                return response
            response = FileResponse(_gui_dist / "index.html")
            response.headers.setdefault("Cache-Control", "no-cache")
            return response

    @application.middleware("http")
    async def admin_auth_middleware(request, call_next):
        if request.url.path.startswith("/admin"):
            from app.api.routes_admin import _require_admin

            try:
                _require_admin(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)

    cfg = load_config()
    if cfg.compatibility.cors_enabled:
        allowed_origins = (
            ["*"]
            if cfg.server.allow_remote_access
            else [
                "http://127.0.0.1:14515",
                "http://localhost:14515",
                "http://127.0.0.1:5173",
                "http://localhost:5173",
                f"http://127.0.0.1:{cfg.server.webui_port}",
                f"http://localhost:{cfg.server.webui_port}",
                "tauri://localhost",
                "http://tauri.localhost",
            ]
        )
        application.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    return application


# 模块级唯一 FastAPI 实例：由工厂函数一次性创建并配置，不再有分散的初始化。
app = create_app()


def _find_available_port(host: str, preferred: int) -> tuple[int, str | None]:
    """优先使用配置端口；不可用时从回退范围中选择随机端口。"""
    import errno
    import socket

    strict_port = os.getenv("KOKOROMEMO_STRICT_PORT", "0").lower() in {"1", "true", "yes"}

    def _try_bind(port: int) -> tuple[bool, OSError | None]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return True, None
        except OSError as exc:
            return False, exc

    ok, preferred_error = _try_bind(preferred)
    if ok:
        return preferred, None
    if strict_port:
        raise RuntimeError(
            f"Configured server port {host}:{preferred} is not available: {_describe_port_unavailable(preferred_error)}"
        ) from preferred_error
    if preferred_error and preferred_error.errno not in {errno.EADDRINUSE, errno.EACCES}:
        raise RuntimeError(
            f"Failed to bind configured server address {host}:{preferred}: {preferred_error}"
        ) from preferred_error
    reason = _describe_port_unavailable(preferred_error)

    import random

    for _ in range(_FALLBACK_PORT_RETRIES):
        port = random.randint(_FALLBACK_PORT_MIN, _FALLBACK_PORT_MAX)  # noqa: S311
        ok, _ = _try_bind(port)
        if ok:
            return port, reason

    # 兜底：交给操作系统决定
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1], reason


def _describe_port_unavailable(error: OSError | None) -> str:
    """描述配置端口不可用的原因。"""
    import errno

    if error is None:
        return "不可用"
    if error.errno == errno.EADDRINUSE:
        return "已被其他进程监听"
    if error.errno == errno.EACCES:
        return "被系统保留或当前用户无权限监听"
    return f"不可用：{error}"


def _write_port_file(port: int) -> None:
    """将实际端口原子写入 .port，供 Tauri 侧发现后端。"""
    try:
        config_path = resolve_config_path(for_write=True)
        base_dir = config_path.parent if config_path else Path.cwd()
        base_dir.mkdir(parents=True, exist_ok=True)
        port_file = base_dir / ".port"
        tmp_file = base_dir / ".port.tmp"
        tmp_file.write_text(str(port), encoding="utf-8")
        tmp_file.replace(port_file)
    except Exception:  # noqa: S110
        pass


if __name__ == "__main__":
    import uvicorn

    load_dotenv()
    cfg = load_config()
    host = cfg.server.host
    port, port_unavailable_reason = _find_available_port(host, cfg.server.port)
    os.environ["KOKOROMEMO_ACTUAL_PORT"] = str(port)
    app.state.actual_port = port
    _write_port_file(port)

    if port != cfg.server.port:
        import logging

        logging.getLogger("kokoromemo").info(
            "配置端口 %d %s，已切换到实际监听端口 %d",
            cfg.server.port,
            port_unavailable_reason or "不可用",
            port,
        )

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=os.getenv("KOKOROMEMO_RELOAD", "0").lower() in {"1", "true", "yes"},
    )
