#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${SAB_SPARK_DB_PATH:-${REPO_ROOT}/data/sab.db}"
KEY_PATH="${SAB_SYSTEM_WITNESS_KEY:-${REPO_ROOT}/data/.sab_system_ed25519.key}"
BACKUP_DIR="${SAB_BACKUP_DIR:-${REPO_ROOT}/data/backups}"
RETENTION_DAYS="${SAB_BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: DB not found at $DB_PATH"
  exit 1
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
DB_BACKUP="${BACKUP_DIR}/sab_${ts}.db"
cp "$DB_PATH" "$DB_BACKUP"

if [[ -f "$KEY_PATH" ]]; then
  cp "$KEY_PATH" "${BACKUP_DIR}/sab_system_key_${ts}.key"
fi

find "$BACKUP_DIR" -type f -name 'sab_*.db' -mtime "+${RETENTION_DAYS}" -delete || true
find "$BACKUP_DIR" -type f -name 'sab_system_key_*.key' -mtime "+${RETENTION_DAYS}" -delete || true

echo "Backup created: $DB_BACKUP"
