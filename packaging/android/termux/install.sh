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
