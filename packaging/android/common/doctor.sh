#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/kokoromemo"
VENV_DIR="$ROOT_DIR/.venv"

echo "KokoroMemo Android Doctor"
echo "Root: $ROOT_DIR"
echo "Arch: $(uname -m)"
echo "Python: $($VENV_DIR/bin/python --version 2>/dev/null || python --version 2>/dev/null || echo missing)"

check_path() {
  if [[ -e "$1" ]]; then
    echo "[OK] $2: $1"
  else
    echo "[FAIL] $2: $1"
  fi
}

check_path "$APP_DIR/app/main.py" "后端源码"
check_path "$ROOT_DIR/webui/dist/index.html" "预构建 Web UI"
check_path "$ROOT_DIR/config.yaml" "配置文件"
check_path "$VENV_DIR/bin/python" "虚拟环境"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  "$VENV_DIR/bin/python" - <<'PY'
mods = ["fastapi", "uvicorn", "wsproto", "httpx", "yaml", "aiosqlite", "pydantic"]
for mod in mods:
    try:
        __import__(mod)
        print(f"[OK] Python module: {mod}")
    except Exception as exc:
        print(f"[FAIL] Python module: {mod}: {exc}")
PY
fi

if [[ -x "$VENV_DIR/bin/python" ]]; then
  "$VENV_DIR/bin/python" - "$ROOT_DIR/config.yaml" <<'PY'
from pathlib import Path
import socket
import sys
import urllib.request
import yaml

config_path = Path(sys.argv[1])
try:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
except Exception as exc:
    print(f"[FAIL] Read config: {exc}")
    raise SystemExit(0)

server = data.get("server") or {}
host = server.get("host", "127.0.0.1")
port = int(server.get("port", 14514))
print(f"[INFO] Configured listen: {host}:{port}")
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as response:
        print(f"[OK] Health: http://127.0.0.1:{port}/health -> {response.status}")
except Exception as exc:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        in_use = sock.connect_ex(("127.0.0.1", port)) == 0
    if in_use:
        print(f"[WARN] Port {port} is occupied but KokoroMemo /health is not ready: {exc}")
    else:
        print(f"[INFO] Port {port} is free; run bash start.sh to start KokoroMemo")
PY
fi

