#!/data/data/com.termux/files/usr/bin/bash
# KokoroMemo Termux 一键安装脚本。
# 用法：curl -fsSL <脚本地址> | bash
set -euo pipefail

REPO="${KOKOROMEMO_UPDATE_REPO:-CyrilPeng/KokoroMemo}"
GITEE_REPO="${KOKOROMEMO_UPDATE_GITEE_REPO:-$REPO}"
INSTALL_DIR="${KOKOROMEMO_INSTALL_DIR:-$HOME/kokoromemo}"
TMP_BASE="${TMPDIR:-${PREFIX:-/tmp}/tmp}"
TMP_DIR="$TMP_BASE/kokoromemo-install"
MANIFEST_FILE="$TMP_DIR/latest.json"

MANIFEST_URLS=(
  "https://github.com/$REPO/releases/latest/download/latest.json"
  "https://gh-proxy.org/https://github.com/$REPO/releases/latest/download/latest.json"
  "https://gitee.com/$GITEE_REPO/raw/main/latest.json"
)

echo "=== KokoroMemo Termux 一键安装 ==="

if [[ -z "${PREFIX:-}" || "$PREFIX" != *"com.termux"* ]]; then
  echo "请在 Termux 原生环境中运行此脚本。"
  exit 1
fi

ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  echo "当前设备架构为 $ARCH；一键包暂只支持 aarch64/arm64。"
  echo "如需在其他架构运行，请使用 ProotUbuntu 包或源码部署。"
  exit 1
fi

mkdir -p "$TMP_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_base_deps() {
  echo "[1/6] 安装基础依赖..."
  pkg update -y
  pkg install -y curl tar python openssl libffi coreutils
}

download_first() {
  local output="$1"
  shift
  local url
  for url in "$@"; do
    echo "尝试下载: $url"
    if curl -fL --connect-timeout 12 --retry 2 -o "$output" "$url"; then
      echo "下载成功。"
      return 0
    fi
  done
  return 1
}

json_get() {
  local path="$1"
  python - "$MANIFEST_FILE" "$path" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
value = data
for part in sys.argv[2].split('.'):
    if not part:
        continue
    if isinstance(value, list):
        value = value[int(part)]
    else:
        value = value.get(part)
    if value is None:
        break
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
elif value is not None:
    print(value)
PY
}

asset_urls() {
  python - "$MANIFEST_FILE" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
asset = data.get("assets", {}).get("android-termux-aarch64", {})
urls = []
if asset.get("url"):
    urls.append(asset["url"])
for mirror in asset.get("mirrors", []):
    url = mirror.get("url")
    if url and url not in urls:
        urls.append(url)
print("\n".join(urls))
PY
}

sha256_file() {
  if need_cmd sha256sum; then
    sha256sum "$1" | awk '{print $1}'
  else
    python - "$1" <<'PY'
import hashlib
import sys
print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())
PY
  fi
}

backup_existing_install() {
  if [[ ! -d "$INSTALL_DIR" ]]; then
    return
  fi
  local backup_dir="$HOME/kokoromemo-backups"
  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$backup_dir"
  echo "检测到已有安装目录，备份到: $backup_dir/kokoromemo-install-$stamp.tar.gz"
  tar -czf "$backup_dir/kokoromemo-install-$stamp.tar.gz" -C "$(dirname "$INSTALL_DIR")" "$(basename "$INSTALL_DIR")" 2>/dev/null || true
}

stop_existing_install() {
  if [[ -x "$INSTALL_DIR/stop.sh" ]]; then
    echo "停止已有 KokoroMemo 服务..."
    bash "$INSTALL_DIR/stop.sh" || true
  fi
}

preserve_existing_data() {
  rm -rf "$TMP_DIR/preserve"
  mkdir -p "$TMP_DIR/preserve"
  if [[ -f "$INSTALL_DIR/config.yaml" ]]; then
    cp -f "$INSTALL_DIR/config.yaml" "$TMP_DIR/preserve/config.yaml"
  fi
  if [[ -d "$INSTALL_DIR/data" ]]; then
    cp -a "$INSTALL_DIR/data" "$TMP_DIR/preserve/data"
  fi
}

restore_existing_data() {
  if [[ -f "$TMP_DIR/preserve/config.yaml" ]]; then
    cp -f "$TMP_DIR/preserve/config.yaml" "$INSTALL_DIR/config.yaml"
  fi
  if [[ -d "$TMP_DIR/preserve/data" ]]; then
    rm -rf "$INSTALL_DIR/data"
    cp -a "$TMP_DIR/preserve/data" "$INSTALL_DIR/data"
  fi
}

ensure_safe_install_dir() {
  case "$INSTALL_DIR" in
    ""|"/"|"$HOME"|"$PREFIX")
      echo "安装目录不安全: $INSTALL_DIR"
      exit 1
      ;;
  esac
}

create_shortcuts() {
  local bin_dir="${PREFIX:-$HOME/.local}/bin"
  mkdir -p "$bin_dir"
  cat > "$bin_dir/kokoromemo" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="__KOKOROMEMO_INSTALL_DIR__"
cmd="${1:-help}"

case "$cmd" in
  start)
    cd "$APP_DIR"
    bash start.sh
    ;;
  stop)
    cd "$APP_DIR"
    bash stop.sh
    ;;
  restart)
    cd "$APP_DIR"
    bash restart.sh
    ;;
  update|updata)
    cd "$APP_DIR"
    bash update.sh
    ;;
  doctor)
    cd "$APP_DIR"
    bash doctor.sh
    ;;
  backup)
    cd "$APP_DIR"
    bash backup.sh
    ;;
  url)
    port="14514"
    [[ -f "$APP_DIR/.port" ]] && port="$(cat "$APP_DIR/.port")"
    echo "Web UI: http://127.0.0.1:${port}"
    echo "OpenAI Base URL: http://127.0.0.1:${port}/v1"
    ;;
  help|-h|--help)
    cat <<HELP
KokoroMemo Android CLI

用法：kokoromemo <命令>

命令：
  start     启动服务
  stop      停止服务
  restart   重启服务
  update    更新到最新版本
  doctor    诊断环境
  backup    备份配置和数据
  url       显示 Web UI 与 OpenAI Base URL

兼容别名：kokoromemo updata 等价于 kokoromemo update
HELP
    ;;
  *)
    echo "未知命令: $cmd"
    echo "运行 kokoromemo help 查看可用命令。"
    exit 1
    ;;
esac
EOF
  python - "$bin_dir/kokoromemo" "$INSTALL_DIR" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
install_dir = sys.argv[2]
path.write_text(path.read_text(encoding="utf-8").replace("__KOKOROMEMO_INSTALL_DIR__", install_dir), encoding="utf-8")
PY
  chmod +x "$bin_dir/kokoromemo"

  cat > "$HOME/start-kokoromemo" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
kokoromemo start
EOF
  cat > "$HOME/stop-kokoromemo" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
kokoromemo stop
EOF
  cat > "$HOME/update-kokoromemo" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
kokoromemo update
EOF
  chmod +x "$HOME/start-kokoromemo" "$HOME/stop-kokoromemo" "$HOME/update-kokoromemo"
}

install_base_deps

echo "[2/6] 获取最新版本信息..."
if ! download_first "$MANIFEST_FILE" "${MANIFEST_URLS[@]}"; then
  echo "无法获取 latest.json，请检查网络后重试。"
  exit 1
fi

VERSION="$(json_get version)"
ASSET_NAME="$(json_get assets.android-termux-aarch64.name)"
EXPECTED_SHA="$(json_get assets.android-termux-aarch64.sha256)"
if [[ -z "$ASSET_NAME" ]]; then
  echo "更新清单中没有 Android-Termux-aarch64 安装包。"
  exit 1
fi

echo "最新版本: $VERSION"
echo "安装包: $ASSET_NAME"

mapfile -t URLS < <(asset_urls)
ARCHIVE="$TMP_DIR/$ASSET_NAME"

echo "[3/6] 下载安装包..."
if ! download_first "$ARCHIVE" "${URLS[@]}"; then
  echo "下载安装包失败。"
  exit 1
fi

echo "[4/6] 校验安装包..."
ACTUAL_SHA="$(sha256_file "$ARCHIVE")"
if [[ -n "$EXPECTED_SHA" && "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  echo "SHA256 校验失败。"
  echo "期望: $EXPECTED_SHA"
  echo "实际: $ACTUAL_SHA"
  exit 1
fi

echo "[5/6] 解压并安装..."
ensure_safe_install_dir
stop_existing_install
backup_existing_install
preserve_existing_data
rm -rf "$TMP_DIR/extract"
mkdir -p "$TMP_DIR/extract"
tar -xzf "$ARCHIVE" -C "$TMP_DIR/extract"
PACKAGE_ROOT="$(find "$TMP_DIR/extract" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$PACKAGE_ROOT" || ! -f "$PACKAGE_ROOT/install.sh" ]]; then
  echo "安装包结构异常。"
  exit 1
fi

rm -rf "$INSTALL_DIR"
mv "$PACKAGE_ROOT" "$INSTALL_DIR"
restore_existing_data
cd "$INSTALL_DIR"
chmod +x ./*.sh
bash install.sh
create_shortcuts

echo "[6/6] 启动服务..."
bash start.sh

rm -rf "$TMP_DIR"

PORT="14514"
if [[ -f "$INSTALL_DIR/.port" ]]; then
  PORT="$(cat "$INSTALL_DIR/.port")"
fi

cat <<EOF

=== KokoroMemo 安装完成 ===

Web UI: http://127.0.0.1:$PORT
OpenAI Base URL: http://127.0.0.1:$PORT/v1

常用命令：
  kokoromemo start      启动
  kokoromemo stop       停止
  kokoromemo update     更新
  kokoromemo doctor     诊断

建议在 Android 系统设置中将 Termux 电池策略设为“不受限”，并锁定 Termux 通知，避免后台服务被系统杀掉。
EOF
