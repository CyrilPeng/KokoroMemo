#!/data/data/com.termux/files/usr/bin/bash
# KokoroMemo Termux 一键安装脚本。
# 用法：python -c "import urllib.request; print(urllib.request.urlopen('<脚本地址>').read().decode())" | bash
set -euo pipefail

REPO="${KOKOROMEMO_UPDATE_REPO:-CyrilPeng/KokoroMemo}"
GITEE_REPO="${KOKOROMEMO_UPDATE_GITEE_REPO:-Cyril_P/KokoroMemo}"
INSTALL_DIR="${KOKOROMEMO_INSTALL_DIR:-$HOME/kokoromemo}"
TMP_BASE="${TMPDIR:-${PREFIX:-/tmp}/tmp}"
TMP_DIR="$TMP_BASE/kokoromemo-install"
MANIFEST_FILE="$TMP_DIR/latest.json"
FALLBACK_VERSION="${KOKOROMEMO_FALLBACK_VERSION:-0.8.6}"
FALLBACK_PREVIOUS_VERSIONS="${KOKOROMEMO_FALLBACK_PREVIOUS_VERSIONS:-0.8.5 0.8.4}"

MANIFEST_URLS=(
  "https://github.com/$REPO/releases/latest/download/latest.json"
  "https://gh-proxy.org/https://github.com/$REPO/releases/latest/download/latest.json"
)

TERMUX_MAIN_MIRRORS=(
  "https://mirrors.tuna.tsinghua.edu.cn/termux/apt/termux-main"
  "https://mirrors.ustc.edu.cn/termux/apt/termux-main"
  "https://packages.termux.dev/apt/termux-main"
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

set_termux_main_mirror() {
  local mirror="$1"
  local list_file="$PREFIX/etc/apt/sources.list"
  mkdir -p "$(dirname "$list_file")"
  if [[ -f "$list_file" ]]; then
    cp "$list_file" "$list_file.kokoromemo.bak" 2>/dev/null || true
  fi
  printf 'deb %s stable main\n' "$mirror" > "$list_file"
  echo "已切换 Termux main 源: $mirror"
}

pkg_update_with_mirrors() {
  if pkg update -y; then
    return 0
  fi
  echo "当前 Termux 软件源不可用，尝试切换镜像源..."
  local mirror
  for mirror in "${TERMUX_MAIN_MIRRORS[@]}"; do
    set_termux_main_mirror "$mirror"
    if pkg update -y; then
      return 0
    fi
  done
  return 1
}

pkg_install_with_mirrors() {
    if DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      -o Dpkg::Options::="--force-confold" \
      -o Dpkg::Options::="--force-confdef" \
      "$@"; then
      return 0
    fi
  echo "依赖下载失败，尝试切换 Termux 镜像源后重试..."
  local mirror
  for mirror in "${TERMUX_MAIN_MIRRORS[@]}"; do
    set_termux_main_mirror "$mirror"
    apt-get update || continue
    if DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --fix-missing \
      -o Dpkg::Options::="--force-confold" \
      -o Dpkg::Options::="--force-confdef" \
      "$@"; then
      return 0
    fi
  done
  return 1
}

install_base_deps() {
  echo "[1/6] 安装基础依赖..."
  set_termux_main_mirror "${TERMUX_MAIN_MIRRORS[0]}"
  pkg_update_with_mirrors
  pkg_install_with_mirrors python python-pip python-ensurepip-wheels tar
}

python_download() {
  local url="$1"
  local output="$2"
  python - "$url" "$output" <<'PY'
import sys
import urllib.request
import urllib.error

url, output = sys.argv[1], sys.argv[2]
try:
    request = urllib.request.Request(url, headers={"User-Agent": "KokoroMemo-Termux-Setup"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read()
    with open(output, "wb") as file:
        file.write(data)
except Exception as exc:
    print(f"Python download failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
}

download_first() {
  local output="$1"
  shift
  local url
  for url in "$@"; do
    echo "尝试下载: $url"
    if need_cmd curl && curl -fL --connect-timeout 4 --max-time 8 --retry 0 -o "$output" "$url"; then
      echo "下载成功。"
      return 0
    fi
    if need_cmd python && python_download "$url" "$output"; then
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

write_fallback_manifest() {
  local version="${1:-$FALLBACK_VERSION}"
  version="${version#v}"
  local asset_name="KokoroMemo-$version-Android-Termux-aarch64.tar.gz"
  echo "无法获取 latest.json，使用脚本内置版本 v$version 兜底。"
  python - "$MANIFEST_FILE" "$version" "$asset_name" "$REPO" "$GITEE_REPO" <<'PY'
import json
import sys

path, version, asset_name, repo, gitee_repo = sys.argv[1:]
github_url = f"https://github.com/{repo}/releases/download/v{version}/{asset_name}"
gitee_url = f"https://gitee.com/{gitee_repo}/releases/download/v{version}/{asset_name}"
manifest = {
    "version": f"v{version}",
    "assets": {
        "android-termux-aarch64": {
            "name": asset_name,
            "sha256": "",
            "url": gitee_url,
            "mirrors": [
                {"name": "Gitee", "url": gitee_url},
                {"name": "GitHub", "url": github_url},
                {"name": "GitHub Proxy", "url": f"https://gh-proxy.org/{github_url}"},
            ],
        }
    },
}

with open(path, "w", encoding="utf-8") as file:
    json.dump(manifest, file, ensure_ascii=False, indent=2)
    file.write("\n")
PY
}


fallback_versions() {
  local seen=""
  local version
  for version in "$FALLBACK_VERSION" $FALLBACK_PREVIOUS_VERSIONS; do
    version="${version#v}"
    [[ -z "$version" ]] && continue
    case " $seen " in
      *" $version "*) continue ;;
    esac
    seen="$seen $version"
    echo "$version"
  done
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


patch_termux_install_scripts() {
  mkdir -p "$INSTALL_DIR/kokoromemo/requirements"
  cat > "$INSTALL_DIR/kokoromemo/requirements/android-termux.txt" <<'REQ'
# Termux 使用 pydantic v1，避免在 Android 上构建 pydantic-core/Rust 扩展。
# 安装此文件时需使用 pip --no-deps。
annotated-doc>=0.0.2
anyio>=4.0
certifi>=2024.0
click>=8.0
h11>=0.16
httpcore>=1.0
idna>=3.0
sniffio>=1.3
typing-extensions>=4.8
typing-inspection>=0.4
starlette>=0.40,<0.51
pydantic>=1.10.15,<2
fastapi>=0.115,<0.116
uvicorn>=0.30
wsproto>=1.2
httpx>=0.27
pyyaml>=6.0
aiosqlite>=0.20
python-dotenv>=1.0
REQ
  cat > "$INSTALL_DIR/doctor.sh" <<'DOCTOR'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/kokoromemo"
VENV_DIR="$ROOT_DIR/.venv"

echo "KokoroMemo Android Doctor"
echo "Root: $ROOT_DIR"
echo "Arch: $(uname -m)"
echo "Python: $($VENV_DIR/bin/python --version 2>/dev/null || python --version 2>/dev/null || echo missing)"

check_path() {
  if [[ -e "$1" ]]; then
    echo "[OK] $2: $1"
  else
    echo "[FAIL] $2: $1"
  fi
}

check_path "$APP_DIR/app/main.py" "后端源码"
check_path "$ROOT_DIR/webui/dist/index.html" "预构建 网页界面"
check_path "$ROOT_DIR/config.yaml" "配置文件"
check_path "$VENV_DIR/bin/python" "虚拟环境"

if [[ -x "$VENV_DIR/bin/python" ]]; then
  "$VENV_DIR/bin/python" - <<'PY'
mods = ["fastapi", "uvicorn", "wsproto", "httpx", "yaml", "aiosqlite", "pydantic"]
for mod in mods:
    try:
        __import__(mod)
        print(f"[OK] Python module: {mod}")
    except Exception as exc:
        print(f"[FAIL] Python module: {mod}: {exc}")
PY
fi
DOCTOR
  cat > "$INSTALL_DIR/install.sh" <<'INSTALL'
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/kokoromemo"
VENV_DIR="$ROOT_DIR/.venv"
WHEEL_DIR="$ROOT_DIR/wheels/termux-aarch64"
ARCH="$(uname -m)"

if [[ "$ARCH" != "aarch64" ]]; then
  echo "当前设备架构为 $ARCH，此安装包仅支持 Termux aarch64。"
  exit 1
fi

if [[ -z "${PREFIX:-}" || "$PREFIX" != *"com.termux"* ]]; then
  echo "请在 Termux 原生环境中运行此安装脚本。"
  exit 1
fi

echo "=== KokoroMemo Android Termux aarch64 安装 ==="

apt_install() {
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    -o Dpkg::Options::="--force-confold" \
    -o Dpkg::Options::="--force-confdef" \
    "$@"
}

pkg update -y
apt_install python python-pip python-ensurepip-wheels python-numpy

rm -rf "$VENV_DIR"
if ! python -m venv --system-site-packages "$VENV_DIR"; then
  echo "虚拟环境创建失败，尝试补齐 Termux ensurepip 组件后重试..."
  apt_install python-pip python-ensurepip-wheels
  rm -rf "$VENV_DIR"
  python -m venv --system-site-packages "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

PIP_ARGS=()
if [[ -d "$WHEEL_DIR" ]] && compgen -G "$WHEEL_DIR/*.whl" >/dev/null; then
  PIP_ARGS=(--find-links "$WHEEL_DIR")
fi

"$VENV_DIR/bin/python" -m pip install --prefer-binary --no-deps "${PIP_ARGS[@]}" -r "$APP_DIR/requirements/android-termux.txt"
"$VENV_DIR/bin/python" - <<'PY'
import pydantic
version = tuple(int(part) for part in pydantic.__version__.split('.')[:2])
if version >= (2, 0):
    raise SystemExit(f"Termux requires pydantic v1, got {pydantic.__version__}")
print(f"Using Termux-compatible pydantic: {pydantic.__version__}")
PY
"$VENV_DIR/bin/python" -m pip install --no-deps "$APP_DIR"

mkdir -p "$ROOT_DIR/data" "$ROOT_DIR/logs"
if [[ ! -f "$ROOT_DIR/config.yaml" ]]; then
  cp "$ROOT_DIR/config.example.yaml" "$ROOT_DIR/config.yaml"
fi

chmod +x "$ROOT_DIR"/*.sh
bash "$ROOT_DIR/doctor.sh"

echo ""
echo "安装完成。启动命令："
echo "  bash $ROOT_DIR/start.sh"
INSTALL
  chmod +x "$INSTALL_DIR/install.sh"
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
  logs|log)
    log_file="$APP_DIR/logs/server.log"
    if [[ -f "$log_file" ]]; then
      tail -n "${2:-120}" "$log_file"
    else
      echo "未找到日志文件: $log_file"
      echo "请先运行 kokoromemo start；注意文件名是 server.log，不是 sever.log。"
      exit 1
    fi
    ;;
  backup)
    cd "$APP_DIR"
    bash backup.sh
    ;;
  url)
    port="14514"
    [[ -f "$APP_DIR/.port" ]] && port="$(cat "$APP_DIR/.port")"
    echo "网页界面：http://127.0.0.1:${port}"
    echo "OpenAI 基础地址：http://127.0.0.1:${port}/v1"
    ;;
  help|-h|--help)
    cat <<HELP
KokoroMemo Android 命令行工具

用法：kokoromemo <命令>

命令：
  start     启动服务
  stop      停止服务
  restart   重启服务
  update    更新到最新版本
  doctor    诊断环境
  logs      查看后端日志，默认最近 120 行
  backup    备份配置和数据
  url       显示 网页界面 与 OpenAI 基础地址

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

echo "[2/6] 准备安装包信息..."
if [[ "${KOKOROMEMO_USE_LATEST:-0}" == "1" ]]; then
  if ! download_first "$MANIFEST_FILE" "${MANIFEST_URLS[@]}"; then
    write_fallback_manifest "$FALLBACK_VERSION"
  fi
else
  write_fallback_manifest "$FALLBACK_VERSION"
fi

echo "[3/6] 下载安装包..."
ARCHIVE=""
EXPECTED_SHA=""
VERSION=""
ASSET_NAME=""
for fallback_version in "" $(fallback_versions); do
  if [[ -n "$fallback_version" ]]; then
    write_fallback_manifest "$fallback_version"
  fi

  VERSION="$(json_get version)"
  ASSET_NAME="$(json_get assets.android-termux-aarch64.name)"
  EXPECTED_SHA="$(json_get assets.android-termux-aarch64.sha256)"
  if [[ -z "$ASSET_NAME" ]]; then
    echo "更新清单中没有 Android-Termux-aarch64 安装包。"
    continue
  fi

  echo "准备下载版本: $VERSION"
  echo "安装包: $ASSET_NAME"

  mapfile -t URLS < <(asset_urls)
  ARCHIVE="$TMP_DIR/$ASSET_NAME"
  if download_first "$ARCHIVE" "${URLS[@]}"; then
    break
  fi

  echo "版本 $VERSION 的安装包暂不可用，尝试下一个稳定版本..."
  ARCHIVE=""
done

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "下载安装包失败：所有候选版本都不可用。"
  echo "如果最新版本正在 GitHub Actions 打包，请稍后重试；也可以设置 KOKOROMEMO_FALLBACK_VERSION 指定已发布版本。"
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
patch_termux_install_scripts
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

网页界面: http://127.0.0.1:$PORT
OpenAI 基础地址: http://127.0.0.1:$PORT/v1

常用命令：
  kokoromemo start      启动
  kokoromemo stop       停止
  kokoromemo update     更新
  kokoromemo doctor     诊断

建议在 Android 系统设置中将 Termux 电池策略设为“不受限”，并锁定 Termux 通知，避免后台服务被系统杀掉。
EOF
