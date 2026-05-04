"""KokoroMemo - Local long-term memory proxy for AI role-playing."""

from __future__ import annotations

import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None  # type: ignore[assignment]


def _read_version() -> str:
    """从 pyproject.toml 读取版本号，作为版本单一来源。"""
    env_version = os.getenv("KOKOROMEMO_VERSION")
    if env_version:
        return env_version.lstrip("v")

    if tomllib is not None:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
                return data.get("project", {}).get("version", "0.0.0")
            except Exception:
                pass
    try:
        from importlib.metadata import version as _get_version
        return _get_version("kokoromemo")
    except Exception:
        pass

    try:
        from app._version import __version__
        return __version__
    except Exception:
        return "0.0.0"

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from app.core.config import load_config, resolve_config_path
from app.core.logging import setup_logging
from app.core.state import set_config
from app.core.time_util import set_configured_timezone


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    cfg = load_config()
    set_config(cfg)
    set_configured_timezone(cfg.server.timezone or None)
    setup_logging(cfg.server.log_level)

    # 确保数据目录存在
    Path(cfg.storage.root_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.root_dir, "conversations").mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.root_dir, "memory").mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.root_dir, "vector_indexes").mkdir(parents=True, exist_ok=True)

    import logging
    logger = logging.getLogger("kokoromemo")
    logger.info("KokoroMemo started on %s:%d", cfg.server.host, cfg.server.port)

    # 安全提醒：未配置管理令牌时绑定非回环地址存在风险。
    if cfg.server.host not in {"127.0.0.1", "localhost", "::1"}:
        if not cfg.server.get_admin_token():
            logger.warning(
                "Server bound to %s without an admin_token; admin endpoints will refuse remote "
                "requests unless server.allow_remote_access is true. Set ADMIN_TOKEN or "
                "admin_token in config to enable secure remote access.",
                cfg.server.host,
            )

    yield

    logger.info("KokoroMemo shutting down")


app = FastAPI(title="KokoroMemo", version=_read_version(), lifespan=lifespan)
app.state.app_version = app.version
app.state.actual_port = None


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    from app.api.routes_admin import router as admin_router
    from app.api.routes_openai import router as openai_router
    from app.api.routes_ws import router as ws_router

    app.include_router(admin_router)
    app.include_router(openai_router)
    app.include_router(ws_router)

    app.add_middleware(GZipMiddleware, minimum_size=1024)

    class CacheStaticFiles(StaticFiles):
        def file_response(self, *args, **kwargs) -> Response:
            response = super().file_response(*args, **kwargs)
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
            return response

    # 如果存在预构建前端，则提供 Vue SPA 静态资源（Web UI / Termux 模式）。
    _web_dist_env = os.getenv("KOKOROMEMO_WEB_DIST", "").strip()
    _gui_dist = Path(_web_dist_env).expanduser() if _web_dist_env else Path(__file__).resolve().parent.parent / "gui" / "dist"
    if _gui_dist.is_dir():
        app.mount("/assets", CacheStaticFiles(directory=_gui_dist / "assets"), name="static-assets")

        _API_PREFIXES = ("/admin", "/v1", "/health", "/ws")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            # 让 API 路由自行处理所属路径
            if any(path.startswith(p.lstrip("/")) for p in _API_PREFIXES):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            file = _gui_dist / path
            if file.is_file():
                response = FileResponse(file)
                response.headers.setdefault("Cache-Control", "public, max-age=3600")
                return response
            response = FileResponse(_gui_dist / "index.html")
            response.headers.setdefault("Cache-Control", "no-cache")
            return response

    @app.middleware("http")
    async def admin_auth_middleware(request, call_next):
        if request.url.path.startswith("/admin"):
            from app.core.state import get_config

            token = get_config().server.get_admin_token()
            if token and request.headers.get("authorization", "") != f"Bearer {token}":
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    cfg = load_config()
    if cfg.compatibility.cors_enabled:
        allowed_origins = ["*"] if cfg.server.allow_remote_access else [
            "http://127.0.0.1:14515",
            "http://localhost:14515",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            f"http://127.0.0.1:{cfg.server.webui_port}",
            f"http://localhost:{cfg.server.webui_port}",
            "tauri://localhost",
            "http://tauri.localhost",
        ]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    return app


# 导入时自动完成 FastAPI 应用配置。
create_app()


def _find_available_port(host: str, preferred: int) -> tuple[int, str | None]:
    """优先使用配置端口；不可用时选择 20000 以上的随机端口。"""
    import errno
    import socket

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
    if preferred_error and preferred_error.errno not in {errno.EADDRINUSE, errno.EACCES}:
        raise RuntimeError(
            f"Failed to bind configured server address {host}:{preferred}: {preferred_error}"
        ) from preferred_error
    reason = _describe_port_unavailable(preferred_error)

    import random
    for _ in range(50):
        port = random.randint(20000, 40000)
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
    """将实际端口写入 .port，供 Tauri 侧发现后端。"""
    try:
        config_path = resolve_config_path(for_write=True)
        base_dir = config_path.parent if config_path else Path.cwd()
        (base_dir / ".port").write_text(str(port), encoding="utf-8")
    except Exception:
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
