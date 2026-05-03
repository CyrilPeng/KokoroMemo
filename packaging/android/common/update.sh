#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$ROOT_DIR/VERSION"
TMP_DIR="$ROOT_DIR/.update-tmp"
BACKUP_DIR="$ROOT_DIR/backups"

REPO="${KOKOROMEMO_UPDATE_REPO:-CyrilPeng/KokoroMemo}"
GITEE_REPO="${KOKOROMEMO_UPDATE_GITEE_REPO:-Cyril_P/KokoroMemo}"
MANIFEST_URLS=(
  "https://github.com/$REPO/releases/latest/download/latest.json"
  "https://gh-proxy.org/https://github.com/$REPO/releases/latest/download/latest.json"
)
GITEE_LATEST_API="https://gitee.com/api/v5/repos/$GITEE_REPO/releases/latest"

CURRENT_VERSION="$(cat "$VERSION_FILE" 2>/dev/null || echo "0.0.0")"
CURRENT_VERSION="${CURRENT_VERSION#v}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令: $1"
    exit 1
  fi
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
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
    if has_cmd curl && curl -fL --connect-timeout 4 --max-time 8 --retry 0 -o "$output" "$url"; then
      echo "下载成功: $url"
      return 0
    fi
    if has_cmd python && python_download "$url" "$output"; then
      echo "下载成功: $url"
      return 0
    fi
  done
  return 1
}

download_gitee_latest_manifest() {
  local output="$1"
  local tag_file="$TMP_DIR/gitee-release.json"
  local urls=()

  echo "尝试通过 Gitee API 获取最新版本..."
  if ! download_first "$tag_file" "$GITEE_LATEST_API"; then
    return 1
  fi

  mapfile -t urls < <(python - "$tag_file" "$GITEE_REPO" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
gitee_repo = sys.argv[2]
tag = data.get("tag_name") or data.get("name") or ""
for item in data.get("attach_files") or data.get("assets") or []:
    name = item.get("name") or item.get("filename") or ""
    if name == "latest.json":
        for key in ("browser_download_url", "download_url", "url", "html_url"):
            url = item.get(key)
            if url:
                print(url)
if tag:
    print(f"https://gitee.com/{gitee_repo}/releases/download/{tag}/latest.json")
PY
)
  if [[ "${#urls[@]}" -eq 0 ]]; then
    return 1
  fi

  download_first "$output" "${urls[@]}"
}

python_download() {
  local url="$1"
  local output="$2"
  python - "$url" "$output" <<'PY'
import sys
import urllib.request

url, output = sys.argv[1], sys.argv[2]
try:
    request = urllib.request.Request(url, headers={"User-Agent": "KokoroMemo-Android-Updater"})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read()
    with open(output, "wb") as file:
        file.write(data)
except Exception as exc:
    print(f"Python download failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
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

require_cmd python
mkdir -p "$TMP_DIR" "$BACKUP_DIR"

echo "当前版本: v$CURRENT_VERSION"
if ! download_first "$TMP_DIR/latest.json" "${MANIFEST_URLS[@]}"; then
  if ! download_gitee_latest_manifest "$TMP_DIR/latest.json"; then
    echo "无法获取更新清单，请稍后重试。"
    exit 1
  fi
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
