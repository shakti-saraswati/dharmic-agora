#!/usr/bin/env bash
set -euo pipefail

AGNI_USER="${AGNI_USER:-openclaw}"
AGNI_HOST="${AGNI_HOST:-157.245.193.15}"
AGNI_REPO_PATH="${AGNI_REPO_PATH:-/home/openclaw/repos/saraswati-dharmic-agora}"
AGNI_BRANCH="${AGNI_BRANCH:-main}"
AGNI_SERVICE_NAME="${AGNI_SERVICE_NAME:-sab-app.service}"
AGNI_DEPLOY_USE_SUDO="${AGNI_DEPLOY_USE_SUDO:-1}"
AGNI_INSTALL_NGINX="${AGNI_INSTALL_NGINX:-0}"

SUDO=""
if [[ "$AGNI_DEPLOY_USE_SUDO" == "1" ]]; then
  SUDO="sudo"
fi

echo "Deploying SAB to ${AGNI_USER}@${AGNI_HOST} (${AGNI_REPO_PATH})"

ssh "${AGNI_USER}@${AGNI_HOST}" bash -s -- \
  "$AGNI_REPO_PATH" "$AGNI_BRANCH" "$AGNI_SERVICE_NAME" "$SUDO" "$AGNI_INSTALL_NGINX" <<'REMOTE'
set -euo pipefail

REPO_PATH="$1"
BRANCH="$2"
SERVICE_NAME="$3"
SUDO="$4"
INSTALL_NGINX="$5"

cd "$REPO_PATH"

PREV_SHA="$(git rev-parse HEAD)"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
NEW_SHA="$(git rev-parse HEAD)"

python3 -m pip install -r requirements.txt
mkdir -p data/deploy_backups

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) prev=${PREV_SHA} new=${NEW_SHA}" >> data/deploy_backups/deploy_history.log

echo "$PREV_SHA" > data/deploy_backups/last_prev_sha

echo "$NEW_SHA" > data/deploy_backups/last_new_sha

if [[ -n "$SUDO" ]]; then
  $SUDO cp deploy/systemd/sab-app.service /etc/systemd/system/"$SERVICE_NAME"
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable "$SERVICE_NAME"
  $SUDO systemctl restart "$SERVICE_NAME"
  $SUDO systemctl --no-pager --full status "$SERVICE_NAME" | head -n 40

  if [[ "$INSTALL_NGINX" == "1" ]]; then
    $SUDO cp deploy/nginx/sab.conf /etc/nginx/sites-available/sab.conf
    $SUDO ln -sf /etc/nginx/sites-available/sab.conf /etc/nginx/sites-enabled/sab.conf
    $SUDO nginx -t
    $SUDO systemctl reload nginx
  fi
else
  echo "INFO: AGNI_DEPLOY_USE_SUDO=0, skipping systemd/nginx install."
  echo "Run manually:"
  echo "  sudo cp deploy/systemd/sab-app.service /etc/systemd/system/${SERVICE_NAME}"
  echo "  sudo systemctl daemon-reload && sudo systemctl restart ${SERVICE_NAME}"
fi

echo "Deploy complete: ${PREV_SHA} -> ${NEW_SHA}"
REMOTE
