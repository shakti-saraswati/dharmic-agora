#!/usr/bin/env bash
set -euo pipefail

AGNI_USER="${AGNI_USER:-openclaw}"
AGNI_HOST="${AGNI_HOST:-157.245.193.15}"
AGNI_REPO_PATH="${AGNI_REPO_PATH:-/home/openclaw/repos/saraswati-dharmic-agora}"
AGNI_SERVICE_NAME="${AGNI_SERVICE_NAME:-sab-app.service}"
AGNI_DEPLOY_USE_SUDO="${AGNI_DEPLOY_USE_SUDO:-1}"
ROLLBACK_SHA="${1:-}"

SUDO=""
if [[ "$AGNI_DEPLOY_USE_SUDO" == "1" ]]; then
  SUDO="sudo"
fi

ssh "${AGNI_USER}@${AGNI_HOST}" bash -s -- \
  "$AGNI_REPO_PATH" "$AGNI_SERVICE_NAME" "$SUDO" "$ROLLBACK_SHA" <<'REMOTE'
set -euo pipefail

REPO_PATH="$1"
SERVICE_NAME="$2"
SUDO="$3"
ROLLBACK_SHA="$4"

cd "$REPO_PATH"

if [[ -z "$ROLLBACK_SHA" ]]; then
  if [[ -f data/deploy_backups/last_prev_sha ]]; then
    ROLLBACK_SHA="$(cat data/deploy_backups/last_prev_sha)"
  else
    echo "ERROR: no rollback SHA provided and no data/deploy_backups/last_prev_sha found"
    exit 1
  fi
fi

CURRENT_SHA="$(git rev-parse HEAD)"

git fetch origin
git checkout "$ROLLBACK_SHA"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback from=${CURRENT_SHA} to=${ROLLBACK_SHA}" >> data/deploy_backups/deploy_history.log

if [[ -n "$SUDO" ]]; then
  $SUDO systemctl restart "$SERVICE_NAME"
  $SUDO systemctl --no-pager --full status "$SERVICE_NAME" | head -n 40
else
  echo "INFO: AGNI_DEPLOY_USE_SUDO=0, skipping service restart."
  echo "Run manually: sudo systemctl restart ${SERVICE_NAME}"
fi

echo "Rollback complete: ${CURRENT_SHA} -> ${ROLLBACK_SHA}"
REMOTE
