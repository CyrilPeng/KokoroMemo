#!/data/data/com.termux/files/usr/bin/bash
# KokoroMemo Termux 一键部署脚本
# 通过 proot-distro 运行完整 Ubuntu 环境，避免 Termux 原生依赖编译问题
set -e

echo "=== KokoroMemo Termux 部署 ==="
echo ""

# 1. 安装 proot-distro 和 Ubuntu
echo "[1/3] 安装 proot-distro + Ubuntu..."
apt update -y && apt full-upgrade -y
pkg install -y proot-distro git
proot-distro install ubuntu 2>/dev/null || echo "  Ubuntu 已安装，跳过。"

# 2. 将部署脚本复制到 Ubuntu 并执行
echo "[2/3] 在 Ubuntu 环境中部署..."
# 克隆项目（如果不存在），用 Termux 的 git（支持更好的网络处理）
INSTALL_DIR="$HOME/kokoromemo"
if [ ! -d "$INSTALL_DIR/.git" ]; then
    echo "  克隆项目..."
    CLONE_URLS=(
        "https://github.com/CyrilPeng/KokoroMemo.git"
        "https://gh-proxy.org/https://github.com/CyrilPeng/KokoroMemo.git"
        "https://gitee.com/Cyril_P/KokoroMemo.git"
    )
    CLONED=false
    for url in "${CLONE_URLS[@]}"; do
        echo "    尝试: ${url}"
        if git clone "$url" "$INSTALL_DIR" 2>&1; then
            CLONED=true
            break
        fi
        rm -rf "$INSTALL_DIR"
        echo "    失败，尝试下一个源..."
    done
    if ! $CLONED; then
        echo "  所有克隆源均失败，请检查网络。"
        exit 1
    fi
fi

# proot-distro 默认共享 Termux home 目录，直接在 Ubuntu 内执行
proot-distro login ubuntu -- bash -c "
cd /data/data/com.termux/files/home/kokoromemo && bash scripts/ubuntu-setup.sh
"

# 3. 创建启动脚本
echo "[3/3] 创建启动脚本..."
cat > "$HOME/start-kokoromemo" << 'SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
# 启动 KokoroMemo（在 Ubuntu proot 环境中运行）
echo "启动 KokoroMemo..."
proot-distro login ubuntu -- bash -c "
cd /data/data/com.termux/files/home/kokoromemo
python3 -m app.main
"
SCRIPT
chmod +x "$HOME/start-kokoromemo"

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
