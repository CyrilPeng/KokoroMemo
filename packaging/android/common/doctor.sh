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
mods = ["fastapi", "uvicorn", "httpx", "yaml", "aiosqlite", "pydantic"]
for mod in mods:
    try:
        __import__(mod)
        print(f"[OK] Python module: {mod}")
    except Exception as exc:
        print(f"[FAIL] Python module: {mod}: {exc}")
PY
fi

