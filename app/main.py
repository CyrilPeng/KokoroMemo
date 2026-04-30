"""KokoroMemo - Local long-term memory proxy for AI role-playing."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import load_config
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

    # Ensure data directories exist
    Path(cfg.storage.root_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.root_dir, "conversations").mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.root_dir, "memory").mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.root_dir, "vector_indexes").mkdir(parents=True, exist_ok=True)

    import logging
    logger = logging.getLogger("kokoromemo")
    logger.info("KokoroMemo started on %s:%d", cfg.server.host, cfg.server.port)

    yield

    logger.info("KokoroMemo shutting down")


app = FastAPI(title="KokoroMemo", version="0.2.3", lifespan=lifespan)


def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""
    from app.api.routes_admin import router as admin_router
    from app.api.routes_openai import router as openai_router
    from app.api.routes_ws import router as ws_router

    app.include_router(admin_router)
    app.include_router(openai_router)
    app.include_router(ws_router)

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


# Auto-configure on import for uvicorn
create_app()


def _find_available_port(host: str, preferred: int) -> int:
    """Return preferred port if free, otherwise pick a random port above 20000."""
    import socket

    def _try_bind(port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return True
        except OSError:
            return False

    if _try_bind(preferred):
        return preferred

    import random
    for _ in range(50):
        port = random.randint(20000, 40000)
        if _try_bind(port):
            return port

    # Fallback: let the OS decide
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _write_port_file(port: int) -> None:
    """Write actual port to .port file for Tauri sidecar discovery."""
    try:
        Path(".port").write_text(str(port), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    load_dotenv()
    cfg = load_config()
    host = cfg.server.host
    port = _find_available_port(host, cfg.server.port)
    _write_port_file(port)

    if port != cfg.server.port:
        import logging
        logging.getLogger("kokoromemo").info(
            "端口 %d 被占用，已切换到 %d", cfg.server.port, port
        )

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
    )
