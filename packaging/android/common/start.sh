#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/kokoromemo"
VENV_DIR="$ROOT_DIR/.venv"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/server.log"
PID_FILE="$ROOT_DIR/kokoromemo.pid"

mkdir -p "$LOG_DIR"

read_port() {
  local port=""
  if [[ -f "$ROOT_DIR/.port" ]]; then
    port="$(cat "$ROOT_DIR/.port" 2>/dev/null || true)"
  elif [[ -f "$APP_DIR/.port" ]]; then
    port="$(cat "$APP_DIR/.port" 2>/dev/null || true)"
    cp "$APP_DIR/.port" "$ROOT_DIR/.port" 2>/dev/null || true
  fi
  if [[ "$port" =~ ^[0-9]+$ ]]; then
    echo "$port"
  else
    echo "14514"
  fi
}

health_ok() {
  local port="$1"
  "$VENV_DIR/bin/python" - "$port" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

port = sys.argv[1]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1.5) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

print_urls() {
  local port="$1"
  echo "网页界面：http://127.0.0.1:${port}"
  echo "OpenAI 基础地址：http://127.0.0.1:${port}/v1"
  echo "日志：$LOG_FILE"
}

show_failure_log() {
  echo "KokoroMemo 启动失败：后端没有变为可访问状态。"
  echo "日志：$LOG_FILE"
  echo "提示：日志文件名是 server.log，不是 sever.log。"
  if [[ -f "$LOG_FILE" ]]; then
    echo "--- 最近 80 行日志 ---"
    tail -n 80 "$LOG_FILE" || true
  else
    echo "server.log 未创建，请检查安装目录是否可写。"
  fi
}

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "未找到虚拟环境，请先运行：bash install.sh"
  exit 1
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    PORT="$(read_port)"
    if health_ok "$PORT"; then
      echo "KokoroMemo 已在运行，PID=$OLD_PID"
      print_urls "$PORT"
      exit 0
    fi
    echo "发现旧进程 PID=$OLD_PID，但 /health 不可访问，正在重启..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

export KOKOROMEMO_WEB_DIST="$ROOT_DIR/webui/dist"
export KOKOROMEMO_CONFIG="$ROOT_DIR/config.yaml"
export KOKOROMEMO_CONFIG_PATH="$ROOT_DIR/config.yaml"
export KOKOROMEMO_RELOAD=0
export PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}"

rm -f "$ROOT_DIR/.port" "$APP_DIR/.port"
: > "$LOG_FILE"

cd "$APP_DIR"
nohup "$VENV_DIR/bin/python" -m app.main > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
PID="$(cat "$PID_FILE")"

PORT="14514"
for _ in $(seq 1 60); do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    show_failure_log
    exit 1
  fi

  PORT="$(read_port)"
  if health_ok "$PORT"; then
    echo "KokoroMemo 已启动，PID=$PID"
    print_urls "$PORT"
    exit 0
  fi
  sleep 0.25
done

show_failure_log
exit 1
