#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$ROOT_DIR/stop.sh"
bash "$ROOT_DIR/start.sh"

