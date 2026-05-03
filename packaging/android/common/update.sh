#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$ROOT_DIR/VERSION"
TMP_DIR="$ROOT_DIR/.update-tmp"
BACKUP_DIR="$ROOT_DIR/backups"

REPO="${KOKOROMEMO_UPDATE_REPO:-CyrilPeng/KokoroMemo}"
GITEE_REPO="${KOKOROMEMO_UPDATE_GITEE_REPO:-$REPO}"
MANIFEST_URLS=(
  "https://github.com/$REPO/releases/latest/download/latest.json"
  "https://gh-proxy.org/https://github.com/$REPO/releases/latest/download/latest.json"
  "https://gitee.com/$GITEE_REPO/raw/main/latest.json"
)

CURRENT_VERSION="$(cat "$VERSION_FILE" 2>/dev/null || echo "0.0.0")"
CURRENT_VERSION="${CURRENT_VERSION#v}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令: $1"
    exit 1
  fi
}

version_gt() {
  local newest="${1#v}"
  local current="${2#v}"
  [[ "$(printf '%s\n%s\n' "$current" "$newest" | sort -V | tail -n 1)" == "$newest" && "$newest" != "$current" ]]
}

detect_asset_key() {
  local arch
  arch="$(uname -m)"
  if [[ "$arch" != "aarch64" && "$arch" != "arm64" ]]; then
    echo "当前仅支持 Android aarch64/arm64，检测到: $arch" >&2
    exit 1
  fi
  if [[ -f "$ROOT_DIR/ANDROID_RUNTIME" ]]; then
    case "$(cat "$ROOT_DIR/ANDROID_RUNTIME")" in
      Termux) echo "android-termux-aarch64" ;;
      ProotUbuntu) echo "android-prootubuntu-aarch64" ;;
      *) echo "未知 ANDROID_RUNTIME: $(cat "$ROOT_DIR/ANDROID_RUNTIME")" >&2; exit 1 ;;
    esac
  elif [[ "$PREFIX" == *com.termux* ]]; then
    echo "android-termux-aarch64"
  else
    echo "android-prootubuntu-aarch64"
  fi
}

download_first() {
  local output="$1"
  shift
  local url
  for url in "$@"; do
    echo "尝试下载: $url"
    if curl -fL --connect-timeout 12 --retry 2 -o "$output" "$url"; then
      echo "下载成功: $url"
      return 0
    fi
  done
  return 1
}

json_get() {
  local path="$1"
  python - "$TMP_DIR/latest.json" "$path" <<'PY'
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
  local key="$1"
  python - "$TMP_DIR/latest.json" "$key" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
asset = data.get("assets", {}).get(sys.argv[2], {})
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
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    python - "$1" <<'PY'
import hashlib
import sys
print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())
PY
  fi
}

require_cmd curl
require_cmd python
mkdir -p "$TMP_DIR" "$BACKUP_DIR"

echo "当前版本: v$CURRENT_VERSION"
if ! download_first "$TMP_DIR/latest.json" "${MANIFEST_URLS[@]}"; then
  echo "无法获取更新清单，请稍后重试。"
  exit 1
fi

LATEST_VERSION="$(json_get version)"
LATEST_VERSION="${LATEST_VERSION#v}"
ASSET_KEY="$(detect_asset_key)"

echo "最新版本: v$LATEST_VERSION"
echo "运行环境: $ASSET_KEY"

if ! version_gt "$LATEST_VERSION" "$CURRENT_VERSION"; then
  echo "已是最新版本。"
  exit 0
fi

mapfile -t URLS < <(asset_urls "$ASSET_KEY")
if [[ "${#URLS[@]}" -eq 0 ]]; then
  echo "更新清单中没有适合当前环境的安装包: $ASSET_KEY"
  exit 1
fi

ASSET_NAME="$(json_get "assets.$ASSET_KEY.name")"
EXPECTED_SHA="$(json_get "assets.$ASSET_KEY.sha256")"
ARCHIVE="$TMP_DIR/$ASSET_NAME"

if ! download_first "$ARCHIVE" "${URLS[@]}"; then
  echo "下载安装包失败。"
  exit 1
fi

ACTUAL_SHA="$(sha256_file "$ARCHIVE")"
if [[ -n "$EXPECTED_SHA" && "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  echo "SHA256 校验失败。"
  echo "期望: $EXPECTED_SHA"
  echo "实际: $ACTUAL_SHA"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
DATA_BACKUP="$BACKUP_DIR/kokoromemo-before-update-$STAMP.tar.gz"
PROGRAM_BACKUP="$BACKUP_DIR/kokoromemo-program-$CURRENT_VERSION-$STAMP.tar.gz"

echo "停止当前服务..."
bash "$ROOT_DIR/stop.sh" || true

echo "备份用户数据: $DATA_BACKUP"
tar -czf "$DATA_BACKUP" -C "$ROOT_DIR" config.yaml data 2>/dev/null || true

echo "备份当前程序: $PROGRAM_BACKUP"
tar -czf "$PROGRAM_BACKUP" -C "$ROOT_DIR" kokoromemo webui *.sh VERSION ANDROID_RUNTIME config.example.yaml 2>/dev/null || true

EXTRACT_DIR="$TMP_DIR/extract"
rm -rf "$EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
tar -xzf "$ARCHIVE" -C "$EXTRACT_DIR"
NEW_ROOT="$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$NEW_ROOT" || ! -d "$NEW_ROOT/kokoromemo" ]]; then
  echo "安装包结构异常。"
  exit 1
fi

echo "替换程序文件..."
rm -rf "$ROOT_DIR/kokoromemo" "$ROOT_DIR/webui" "$ROOT_DIR/wheels"
cp -a "$NEW_ROOT/kokoromemo" "$ROOT_DIR/kokoromemo"
cp -a "$NEW_ROOT/webui" "$ROOT_DIR/webui"
[[ -d "$NEW_ROOT/wheels" ]] && cp -a "$NEW_ROOT/wheels" "$ROOT_DIR/wheels"
cp -f "$NEW_ROOT"/*.sh "$ROOT_DIR/"
cp -f "$NEW_ROOT/VERSION" "$ROOT_DIR/VERSION"
cp -f "$NEW_ROOT/ANDROID_RUNTIME" "$ROOT_DIR/ANDROID_RUNTIME" 2>/dev/null || true
cp -f "$NEW_ROOT/config.example.yaml" "$ROOT_DIR/config.example.yaml" 2>/dev/null || true
chmod +x "$ROOT_DIR"/*.sh

echo "检查 Python 依赖..."
bash "$ROOT_DIR/install.sh"

echo "启动新版本..."
if bash "$ROOT_DIR/start.sh"; then
  rm -rf "$TMP_DIR"
  echo "更新完成: v$CURRENT_VERSION -> v$LATEST_VERSION"
  exit 0
fi

echo "新版本启动失败，请使用以下备份手动恢复:"
echo "$PROGRAM_BACKUP"
exit 1
