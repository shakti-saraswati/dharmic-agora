#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SMOKE_BASE_URL:-http://127.0.0.1:18080}"
ROOT_PATH="${SMOKE_ROOT_PATH:-/}"
STATUS_PATH="${SMOKE_STATUS_PATH:-/api/node/status}"
TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-90}"

if [[ "${ROOT_PATH:0:1}" != "/" ]]; then
  ROOT_PATH="/${ROOT_PATH}"
fi
if [[ "${STATUS_PATH:0:1}" != "/" ]]; then
  STATUS_PATH="/${STATUS_PATH}"
fi

echo "deploy_smoke_check:"
echo "  base_url=${BASE_URL}"
echo "  root_path=${ROOT_PATH}"
echo "  status_path=${STATUS_PATH}"
echo "  timeout_seconds=${TIMEOUT_SECONDS}"

for _ in $(seq 1 "${TIMEOUT_SECONDS}"); do
  code="$(curl -sS -o /dev/null -w "%{http_code}" "${BASE_URL}${STATUS_PATH}" || true)"
  if [[ "${code}" == "200" ]]; then
    break
  fi
  sleep 1
done

ROOT_CODE="$(curl -sS -o /dev/null -w "%{http_code}" "${BASE_URL}${ROOT_PATH}")"
STATUS_CODE="$(curl -sS -o /dev/null -w "%{http_code}" "${BASE_URL}${STATUS_PATH}")"

echo "  root_code=${ROOT_CODE}"
echo "  status_code=${STATUS_CODE}"

if [[ "${ROOT_CODE}" != "200" || "${STATUS_CODE}" != "200" ]]; then
  echo "ERROR: deploy smoke failed" >&2
  exit 1
fi

echo "deploy_smoke_check: pass"
