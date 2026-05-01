#!/data/data/com.termux/files/usr/bin/bash
# KokoroMemo Termux 一键部署脚本
# 用法: bash termux-setup.sh
set -e

echo "=== KokoroMemo Termux 部署 ==="
echo ""

# 1. 系统依赖
echo "[1/5] 安装系统依赖..."
pkg update -y
pkg install -y python git

# 2. 克隆项目
INSTALL_DIR="$HOME/kokoromemo"
if [ -d "$INSTALL_DIR" ]; then
    echo "[2/5] 项目目录已存在，更新中..."
    cd "$INSTALL_DIR" && git pull
else
    echo "[2/5] 克隆项目..."
    git clone https://github.com/CyrilPeng/KokoroMemo.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Python 依赖
echo "[3/5] 安装 Python 依赖..."
pip install -e . 2>&1 | tail -3

# 4. 检查前端构建产物
if [ -d "gui/dist" ] && [ -f "gui/dist/index.html" ]; then
    echo "[4/5] 前端构建产物已存在，跳过构建。"
else
    echo "[4/5] 前端构建产物不存在。"
    echo "      选项 A: 在 PC 上运行 'cd gui && npm run build'，将 dist/ 目录拷贝到手机"
    echo "      选项 B: 安装 Node.js 构建（较慢）:"
    echo "        pkg install nodejs-lts"
    echo "        cd gui && npm install && npm run build"
    echo ""
    read -p "是否安装 Node.js 并构建前端？(y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pkg install -y nodejs-lts
        cd gui && npm install && npm run build && cd ..
    else
        echo "请手动将 gui/dist 目录放到 $INSTALL_DIR/gui/dist"
        exit 1
    fi
fi

# 5. 配置
echo "[5/5] 配置..."
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

echo ""
echo "=== 部署完成 ==="
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
