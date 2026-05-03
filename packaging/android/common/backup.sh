#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$ROOT_DIR/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/kokoromemo-data-$STAMP.tar.gz" -C "$ROOT_DIR" config.yaml data 2>/dev/null || true
echo "备份完成: $BACKUP_DIR/kokoromemo-data-$STAMP.tar.gz"

