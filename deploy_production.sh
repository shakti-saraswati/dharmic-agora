#!/usr/bin/env bash
set -euo pipefail

# dharmic-agora production deploy helper
# - pre-flight validation
# - optional backup
# - start uvicorn
# - basic health check

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [[ ! -f .env.production ]]; then
  echo "ERROR: .env.production missing"
  exit 1
fi

# Load env (safe: template may contain placeholders)
set -a
# shellcheck disable=SC1091
source .env.production
set +a

python3 -m compileall -q agora || {
  echo "ERROR: Python compile failed"
  exit 1
}

# Optional backup: sqlite file if present
TS="$(date -u +%Y%m%d_%H%M%SZ)"
if [[ -f agora.db ]]; then
  mkdir -p backups
  cp -a agora.db "backups/agora_${TS}.db"
  echo "Backup: backups/agora_${TS}.db"
fi

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

echo "Starting dharmic-agora on ${HOST}:${PORT} (ENV=${ENV:-unset})"

# NOTE: TLS is typically terminated at nginx/caddy. ENFORCE_HTTPS should be used behind a proxy.
exec uvicorn agora.api_server:app --host "$HOST" --port "$PORT"
