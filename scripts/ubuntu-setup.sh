#!/bin/bash
# KokoroMemo 依赖安装脚本
# 在 proot-distro Ubuntu 或原生 Termux 中执行
# 用法: bash ubuntu-setup.sh [--webui-only]
set -e

WEBUI_ONLY=false
[ "$1" = "--webui-only" ] && WEBUI_ONLY=true

# 自动检测目录和 Python 命令
if [ -d "/data/data/com.termux/files/home/kokoromemo" ]; then
    APP_DIR="/data/data/com.termux/files/home/kokoromemo"
else
    APP_DIR="$HOME/kokoromemo"
fi
cd "$APP_DIR"

# 检测 Python 命令
if command -v python3 &>/dev/null; then
    PY=python3
    PIP="pip3"
else
    PY=python
    PIP="pip"
fi

# proot Ubuntu 需要 --break-system-packages
PIP_FLAGS=""
if [ -f "/etc/os-release" ] && grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    PIP_FLAGS="--break-system-packages"
fi

if ! $WEBUI_ONLY; then
    # 系统依赖（仅 proot Ubuntu）
    if [ -f "/etc/os-release" ] && grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        echo "  [a] 安装 Ubuntu 系统依赖..."
        apt update -y
        apt install -y python3 python3-pip python3-venv git
    fi

    # Python 依赖
    echo "  [b] 安装 Python 依赖..."
    $PIP install $PIP_FLAGS -e . 2>&1 | tail -5
fi

# 下载 Web UI 前端
if [ -d "gui/dist" ] && [ -f "gui/dist/index.html" ]; then
    echo "  [c] 前端构建产物已存在，跳过。"
else
    echo "  [c] 下载 Web UI 前端..."
    VERSION=$($PY -c "
import tomllib, pathlib
p = pathlib.Path('pyproject.toml')
print(tomllib.loads(p.read_text())['project']['version'])
")
    ZIP_NAME="KokoroMemo-${VERSION}-WebUI-dist.zip"
    ZIP_FILE="$HOME/kokoromemo-webui-dist.zip"
    DOWNLOAD_URLS=(
        "https://github.com/CyrilPeng/KokoroMemo/releases/download/v${VERSION}/${ZIP_NAME}"
        "https://gh-proxy.org/https://github.com/CyrilPeng/KokoroMemo/releases/download/v${VERSION}/${ZIP_NAME}"
        "https://gitee.com/Cyril_P/KokoroMemo/releases/download/v${VERSION}/${ZIP_NAME}"
    )

    DOWNLOADED=false
    for url in "${DOWNLOAD_URLS[@]}"; do
        echo "    尝试: ${url}"
        if $PY -c "
import urllib.request, sys
urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
" "$url" "$ZIP_FILE" 2>/dev/null; then
            DOWNLOADED=true
            break
        fi
        echo "    失败，尝试下一个源..."
    done

    if $DOWNLOADED; then
        echo "    解压到 gui/dist/..."
        mkdir -p gui/dist
        $PY -c "
import zipfile, sys
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
" "$ZIP_FILE" gui/dist
        rm -f "$ZIP_FILE"
        # Release zip 可能带 gui/dist/ 前缀，展平
        if [ -d "gui/dist/gui/dist" ]; then
            mv gui/dist/gui/dist/* gui/dist/
            rm -rf gui/dist/gui
        fi
        echo "    Web UI 前端就绪。"
    else
        echo "    所有下载源均失败。后端仍可正常运行，只是无法访问 Web 管理界面。"
    fi
fi

# 配置
if [ ! -f "config.yaml" ]; then
    echo "  [d] 配置..."
    cat > config.yaml << 'YAML'
server:
  host: "0.0.0.0"
  port: 14514

storage:
  root_dir: "./data"
YAML
    echo "    已创建 config.yaml"
fi

echo "  依赖安装完成。"
