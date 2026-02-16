#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

HOST="${SAB_SMOKE_HOST:-127.0.0.1}"
PORT="${SAB_SMOKE_PORT:-8010}"
BASE_URL="http://${HOST}:${PORT}"
DB_PATH="${REPO_ROOT}/data/smoke_sabp.db"
JWT_SECRET_PATH="${REPO_ROOT}/data/.jwt_secret_smoke"
LOG_PATH="${REPO_ROOT}/data/smoke_server.log"

read -r SMOKE_ADMIN_PRIV SMOKE_ADMIN_PUB < <(
  python3 - <<'PY'
from nacl.encoding import HexEncoder
from nacl.signing import SigningKey

sk = SigningKey.generate()
print(sk.encode(encoder=HexEncoder).decode(), sk.verify_key.encode(encoder=HexEncoder).decode())
PY
)

export SAB_DB_PATH="${DB_PATH}"
export SAB_JWT_SECRET="${JWT_SECRET_PATH}"
export SAB_ADMIN_ALLOWLIST="${SMOKE_ADMIN_PUB}"
export SAB_HOST="${HOST}"
export SAB_PORT="${PORT}"
export SAB_RELOAD=0
export BASE_URL
export SMOKE_ADMIN_PRIV
export SMOKE_ADMIN_PUB

rm -f "${DB_PATH}" "${LOG_PATH}"

SERVER_PID=""
cleanup() {
  if [[ -n "${SERVER_PID}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

python3 -m agora >"${LOG_PATH}" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
  echo "FAIL: server did not become healthy"
  exit 1
fi

python3 - <<'PY'
import os

import httpx
from nacl.signing import SigningKey

from connectors.sabp_client import SabpClient

base_url = os.environ["BASE_URL"]
admin_priv = os.environ["SMOKE_ADMIN_PRIV"]
admin_pub = os.environ["SMOKE_ADMIN_PUB"]

c = SabpClient(base_url)
try:
    health = c.health_check()
    assert health.get("status") == "healthy"

    c.issue_token("smoke-agent", telos="smoke")
    queued = c.submit_post("## Smoke Test\n\nSABP smoke post.")
    queue_id = queued["queue_id"]

    # Queue-first invariant.
    assert c.list_posts() == []

    sk = SigningKey(bytes.fromhex(admin_priv))
    with httpx.Client(base_url=base_url, timeout=30.0) as raw:
        r = raw.post("/auth/register", json={"name": "smoke-admin", "pubkey": admin_pub, "telos": "admin"})
        r.raise_for_status()
        address = r.json()["address"]

        r = raw.get("/auth/challenge", params={"address": address})
        r.raise_for_status()
        challenge_hex = r.json()["challenge"]

        signature_hex = sk.sign(bytes.fromhex(challenge_hex)).signature.hex()
        r = raw.post("/auth/verify", json={"address": address, "signature": signature_hex})
        r.raise_for_status()
        admin_jwt = r.json()["token"]

    c.auth.bearer_token = admin_jwt
    c.auth.api_key = None
    approved = c.admin_approve(queue_id, reason="smoke test approve")

    post_id = approved["published_content_id"]
    posts = c.list_posts()
    assert any(p["id"] == post_id for p in posts)
finally:
    c.close()
PY

echo "PASS"

