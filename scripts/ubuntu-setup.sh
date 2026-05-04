#!/bin/bash
# KokoroMemo Ubuntu 安装/校验脚本。
# 适用于 proot-distro Ubuntu，也兼容在源码目录中手动执行。
# 用法：bash ubuntu-setup.sh [--webui-only]
#
# --webui-only 表示“只处理预构建 网页界面 场景”：
#   - 跳过 apt 与 pip 依赖安装；
#   - 仍会校验 网页界面 产物是否存在；
#   - 仍会在缺少 config.yaml 时创建最小配置。
set -e

WEBUI_ONLY=false
if [ "${1:-}" = "--webui-only" ]; then
    WEBUI_ONLY=true
elif [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    sed -n '2,9p' "$0" | sed 's/^# //'
    exit 0
elif [ -n "${1:-}" ]; then
    echo "未知参数：$1"
    echo "用法：bash ubuntu-setup.sh [--webui-only]"
    exit 2
fi

if [ -n "${KOKOROMEMO_APP_DIR:-}" ]; then
    APP_DIR="$KOKOROMEMO_APP_DIR"
elif [ -d "/data/data/com.termux/files/home/kokoromemo" ]; then
    APP_DIR="/data/data/com.termux/files/home/kokoromemo"
else
    APP_DIR="$HOME/kokoromemo"
fi

if [ ! -d "$APP_DIR" ]; then
    echo "未找到 KokoroMemo 目录：$APP_DIR"
    echo "可通过 KOKOROMEMO_APP_DIR 指定项目目录。"
    exit 1
fi
cd "$APP_DIR"

if command -v python3 >/dev/null 2>&1; then
    PIP="pip3"
else
    PIP="pip"
fi

PIP_FLAGS=""
if [ -f "/etc/os-release" ] && grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    PIP_FLAGS="--break-system-packages"
fi

if $WEBUI_ONLY; then
    echo "  [a] --webui-only：跳过 apt 与 pip 依赖安装。"
else
    if [ -f "/etc/os-release" ] && grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        echo "  [a] 安装 Ubuntu 系统依赖..."
        apt update -y
        apt install -y python3 python3-pip python3-venv git
    else
        echo "  [a] 非 Ubuntu 环境，跳过 apt 依赖安装。"
    fi

    echo "  [b] 安装 Python 依赖..."
    $PIP install $PIP_FLAGS -e . 2>&1 | tail -5
fi

if [ -d "webui/dist" ] && [ -f "webui/dist/index.html" ]; then
    echo "  [c] 已找到单包预构建 网页界面：webui/dist"
elif [ -d "gui/dist" ] && [ -f "gui/dist/index.html" ]; then
    echo "  [c] 已找到源码构建 网页界面：gui/dist"
else
    echo "  [c] 未找到 网页界面 产物。"
    echo "      单包部署应包含 webui/dist/index.html；源码部署请先在 gui 目录执行 npm run build。"
    exit 1
fi

if [ ! -f "config.yaml" ]; then
    echo "  [d] 创建最小配置 config.yaml..."
    cat > config.yaml << 'YAML'
server:
  host: "0.0.0.0"
  port: 14514

storage:
  root_dir: "./data"
YAML
    echo "      已创建 config.yaml"
else
    echo "  [d] config.yaml 已存在，跳过创建。"
fi

echo "  Ubuntu 安装/校验完成。"
