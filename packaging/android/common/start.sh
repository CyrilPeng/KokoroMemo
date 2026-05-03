#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/kokoromemo"
VENV_DIR="$ROOT_DIR/.venv"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$ROOT_DIR/kokoromemo.pid"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "KokoroMemo 已在运行，PID=$(cat "$PID_FILE")"
  exit 0
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "未找到虚拟环境，请先运行 bash install.sh"
  exit 1
fi

export KOKOROMEMO_WEB_DIST="$ROOT_DIR/webui/dist"
export KOKOROMEMO_CONFIG="$ROOT_DIR/config.yaml"
export KOKOROMEMO_RELOAD=0
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

cd "$APP_DIR"
nohup "$VENV_DIR/bin/python" -m app.main > "$LOG_DIR/server.log" 2>&1 &
echo $! > "$PID_FILE"

sleep 2
if [[ -f "$ROOT_DIR/.port" ]]; then
  PORT="$(cat "$ROOT_DIR/.port")"
else
  PORT="14514"
fi

echo "KokoroMemo 已启动，PID=$(cat "$PID_FILE")"
echo "Web UI: http://127.0.0.1:${PORT}"
echo "OpenAI Base URL: http://127.0.0.1:${PORT}/v1"
echo "日志: $LOG_DIR/server.log"

