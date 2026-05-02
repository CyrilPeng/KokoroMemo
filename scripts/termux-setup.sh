#!/data/data/com.termux/files/usr/bin/bash
# KokoroMemo Termux 一键部署脚本
# 优先使用 proot-distro Ubuntu（完整 glibc），回退到原生 Termux
set -e

echo "=== KokoroMemo Termux 部署 ==="
echo ""

INSTALL_DIR="$HOME/kokoromemo"
USE_PROOT=false

# --- 克隆项目（无论哪种模式都需要）---
clone_project() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo "  项目目录已存在，更新中..."
        cd "$INSTALL_DIR" && git pull || echo "  git pull 失败，使用当前版本继续。"
        return
    fi
    echo "  克隆项目..."
    CLONE_URLS=(
        "https://github.com/CyrilPeng/KokoroMemo.git"
        "https://gh-proxy.org/https://github.com/CyrilPeng/KokoroMemo.git"
        "https://gitee.com/Cyril_P/KokoroMemo.git"
    )
    for url in "${CLONE_URLS[@]}"; do
        echo "    尝试: ${url}"
        if git clone "$url" "$INSTALL_DIR" 2>&1; then
            return
        fi
        rm -rf "$INSTALL_DIR"
        echo "    失败，尝试下一个源..."
    done
    echo "  所有克隆源均失败，请检查网络。"
    exit 1
}

# --- 创建启动脚本 ---
create_launcher() {
    local mode="$1"
    if [ "$mode" = "proot" ]; then
        cat > "$HOME/start-kokoromemo" << 'SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
echo "启动 KokoroMemo (proot Ubuntu)..."
proot-distro login ubuntu -- bash -c "
cd /data/data/com.termux/files/home/kokoromemo
python3 -m app.main
"
SCRIPT
    else
        cat > "$HOME/start-kokoromemo" << 'SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
echo "启动 KokoroMemo..."
cd ~/kokoromemo
python -m app.main
SCRIPT
    fi
    chmod +x "$HOME/start-kokoromemo"
}

# ========================================
# 1. 系统依赖
# ========================================
echo "[1/4] 安装系统依赖..."
apt update -y && apt full-upgrade -y
pkg install -y git

# 尝试安装 proot-distro
if proot-distro install ubuntu 2>/dev/null; then
    USE_PROOT=true
    echo "  proot-distro Ubuntu 安装成功，使用 Ubuntu 环境。"
else
    echo "  proot-distro 不可用，回退到原生 Termux 环境。"
    # 安装原生 Termux 预编译包
    pkg install -y python python-numpy python-pydantic python-yaml 2>/dev/null || true
fi

# ========================================
# 2. 克隆项目
# ========================================
echo "[2/4] 克隆项目..."
clone_project

# ========================================
# 3. 安装依赖
# ========================================
if $USE_PROOT; then
    echo "[3/4] 在 Ubuntu 环境中安装依赖..."
    proot-distro login ubuntu -- bash -c "
cd /data/data/com.termux/files/home/kokoromemo && bash scripts/ubuntu-setup.sh
"
else
    echo "[3/4] 在 Termux 中安装 Python 依赖..."
    cd "$INSTALL_DIR"
    # pkg 已预装 numpy/pydantic/yaml，pip 装其余纯 Python 包
    pip install -e . 2>&1 | tail -5 || echo "  部分依赖安装失败，核心功能仍可使用。"
    # 下载 Web UI 前端
    bash scripts/ubuntu-setup.sh --webui-only 2>/dev/null || true
fi

# ========================================
# 4. 创建启动脚本
# ========================================
echo "[4/4] 完成..."
create_launcher $( $USE_PROOT && echo "proot" || echo "native" )

echo ""
echo "=== 部署完成 ==="
echo ""
echo "启动方式:"
echo "  ~/start-kokoromemo"
echo ""
echo "手机 AIRP 客户端填: http://127.0.0.1:14514/v1"
echo "Web 管理界面: http://127.0.0.1:14514"
echo ""
echo "保持后台运行（防止 Termux 被杀）:"
echo "  1. Termux 通知栏 → 长按 → 锁定"
echo "  2. 系统设置 → 电池 → Termux → 不受限"
echo ""
