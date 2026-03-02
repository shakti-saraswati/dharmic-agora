#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <backup_db_path> [--force]"
  exit 1
fi

BACKUP_PATH="$1"
FORCE="${2:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${SAB_SPARK_DB_PATH:-${REPO_ROOT}/data/sab.db}"

if [[ ! -f "$BACKUP_PATH" ]]; then
  echo "ERROR: backup not found: $BACKUP_PATH"
  exit 1
fi

if [[ "$FORCE" != "--force" ]]; then
  echo "Refusing to restore without explicit --force"
  echo "Target: $DB_PATH"
  echo "Backup: $BACKUP_PATH"
  exit 1
fi

mkdir -p "$(dirname "$DB_PATH")"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -f "$DB_PATH" ]]; then
  cp "$DB_PATH" "${DB_PATH}.pre_restore_${ts}"
fi

cp "$BACKUP_PATH" "$DB_PATH"

echo "Restore complete: $BACKUP_PATH -> $DB_PATH"
