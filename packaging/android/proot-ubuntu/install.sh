#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/kokoromemo"
VENV_DIR="$ROOT_DIR/.venv"
WHEEL_DIR="$ROOT_DIR/wheels/proot-ubuntu-aarch64"
ARCH="$(uname -m)"

if [[ "$ARCH" != "aarch64" ]]; then
  echo "当前环境架构为 $ARCH，此安装包仅支持 Proot Ubuntu aarch64。"
  exit 1
fi

if [[ -n "${PREFIX:-}" && "$PREFIX" == *"com.termux"* ]]; then
  echo "检测到你仍在 Termux 原生环境。请先进入 proot Ubuntu 后再运行此脚本。"
  exit 1
fi

echo "=== KokoroMemo Android Proot Ubuntu aarch64 安装 ==="

if command -v apt-get >/dev/null 2>&1; then
  apt-get update
  apt-get install -y python3 python3-venv python3-pip
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

PIP_ARGS=()
if [[ -d "$WHEEL_DIR" ]] && compgen -G "$WHEEL_DIR/*.whl" >/dev/null; then
  PIP_ARGS=(--find-links "$WHEEL_DIR")
fi

"$VENV_DIR/bin/python" -m pip install "${PIP_ARGS[@]}" -r "$APP_DIR/requirements/android-proot-ubuntu.txt"
"$VENV_DIR/bin/python" -m pip install "${PIP_ARGS[@]}" "$APP_DIR"

mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/logs"
if [[ ! -f "$ROOT_DIR/config.yaml" ]]; then
  cp "$ROOT_DIR/config.example.yaml" "$ROOT_DIR/config.yaml"
fi

chmod +x "$ROOT_DIR"/*.sh
bash "$ROOT_DIR/doctor.sh"

echo ""
echo "安装完成。启动命令："
echo "  bash $ROOT_DIR/start.sh"

