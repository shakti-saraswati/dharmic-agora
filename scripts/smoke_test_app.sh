#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

HOST="${SAB_SMOKE_HOST:-127.0.0.1}"
PORT="${SAB_SMOKE_PORT:-8012}"
BASE_URL="http://${HOST}:${PORT}"
DB_PATH="${SAB_SMOKE_DB_PATH:-${REPO_ROOT}/data/smoke_spark.db}"
KEY_PATH="${SAB_SMOKE_KEY_PATH:-${REPO_ROOT}/data/.sab_system_ed25519_smoke.key}"
LOG_PATH="${SAB_SMOKE_LOG_PATH:-${REPO_ROOT}/data/smoke_app.log}"

mkdir -p "${REPO_ROOT}/data"
rm -f "$DB_PATH" "$KEY_PATH" "$LOG_PATH"

export SAB_SPARK_DB_PATH="$DB_PATH"
export SAB_SYSTEM_WITNESS_KEY="$KEY_PATH"

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

python3 -m uvicorn agora.app:app --host "$HOST" --port "$PORT" >"$LOG_PATH" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done

curl -fsS "${BASE_URL}/health" >/dev/null
curl -fsS "${BASE_URL}/healthz" >/dev/null
curl -fsS "${BASE_URL}/readyz" >/dev/null
curl -fsS "${BASE_URL}/" >/dev/null
curl -fsS "${BASE_URL}/submit" >/dev/null

headers_file="$(mktemp)"
body_file="$(mktemp)"

curl -sS -D "$headers_file" -o "$body_file" -X POST \
  -d "display_name=smoke-agent" \
  -d "content_type=text" \
  --data-urlencode "content=Smoke test submission from smoke_test_app.sh" \
  "${BASE_URL}/submit"

location="$(awk 'BEGIN{IGNORECASE=1} /^Location:/ {print $2}' "$headers_file" | tr -d '\r')"
if [[ -z "$location" ]]; then
  echo "FAIL: submit did not return a redirect Location"
  exit 1
fi

curl -fsS "${BASE_URL}${location}" >/dev/null

echo "OK: app smoke test passed (${BASE_URL})"
