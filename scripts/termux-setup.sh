#!/data/data/com.termux/files/usr/bin/bash
# KokoroMemo Termux 一键部署脚本
# 用法: bash termux-setup.sh
set -e

echo "=== KokoroMemo Termux 部署 ==="
echo ""

# 1. 系统依赖
echo "[1/6] 安装系统依赖..."
pkg update -y
pkg install -y python git

# 2. 克隆项目
INSTALL_DIR="$HOME/kokoromemo"
CLONE_URLS=(
    "https://github.com/CyrilPeng/KokoroMemo.git"
    "https://gh-proxy.org/https://github.com/CyrilPeng/KokoroMemo.git"
    "https://gitee.com/Cyril_P/KokoroMemo.git"
)
if [ -d "$INSTALL_DIR" ]; then
    echo "[2/6] 项目目录已存在，更新中..."
    cd "$INSTALL_DIR" && git pull || echo "      git pull 失败，使用当前版本继续。"
else
    echo "[2/6] 克隆项目..."
    CLONED=false
    for url in "${CLONE_URLS[@]}"; do
        echo "      尝试: ${url}"
        if git clone "$url" "$INSTALL_DIR" 2>&1; then
            CLONED=true
            break
        fi
        rm -rf "$INSTALL_DIR"
        echo "      失败，尝试下一个源..."
    done
    if ! $CLONED; then
        echo "      所有克隆源均失败，请检查网络。"
        exit 1
    fi
    cd "$INSTALL_DIR"
fi

# 3. Python 依赖
echo "[3/6] 安装 Python 依赖..."
pip install -e . 2>&1 | tail -3

# 4. 下载并解压 Web UI 前端
if [ -d "gui/dist" ] && [ -f "gui/dist/index.html" ]; then
    echo "[4/6] 前端构建产物已存在，跳过。"
else
    echo "[4/6] 下载 Web UI 前端..."
    # 从 pyproject.toml 读取当前版本号
    VERSION=$(python -c "
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

    echo "      版本: v${VERSION}"

    DOWNLOADED=false
    for url in "${DOWNLOAD_URLS[@]}"; do
        echo "      尝试: ${url}"
        if python -c "
import urllib.request, sys
urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
" "$url" "$ZIP_FILE" 2>/dev/null; then
            DOWNLOADED=true
            break
        fi
        echo "      失败，尝试下一个源..."
    done

    if $DOWNLOADED; then
        echo "      解压到 gui/dist/..."
        mkdir -p gui/dist
        python -c "
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
        echo "      Web UI 前端就绪。"
    else
        echo "      所有下载源均失败。后端仍可正常运行（API 代理 + 记忆系统），"
        echo "      只是无法访问 Web 管理界面。"
        echo "      手动下载: https://github.com/CyrilPeng/KokoroMemo/releases/latest"
    fi
fi

# 5. 配置
echo "[5/6] 配置..."
if [ ! -f "config.yaml" ]; then
    cat > config.yaml << 'YAML'
server:
  host: "0.0.0.0"
  port: 14514

storage:
  root_dir: "./data"
YAML
    echo "  已创建 config.yaml（监听 0.0.0.0:14514）"
fi

# 6. 完成
echo ""
echo "=== [6/6] 部署完成 ==="
echo ""
echo "启动方式:"
echo "  cd $INSTALL_DIR"
echo "  python -m app.main"
echo ""
echo "手机 AIRP 客户端填: http://127.0.0.1:14514/v1"
echo "Web 管理界面: http://127.0.0.1:14514"
echo ""
echo "保持后台运行（防止 Termux 被杀）:"
echo "  1. Termux 通知栏 → 长按 → 锁定"
echo "  2. 系统设置 → 电池 → Termux → 不受限"
echo ""
