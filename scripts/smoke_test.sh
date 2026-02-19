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
SHADOW_DIR="${REPO_ROOT}/agora/logs/shadow_loop"
SHADOW_SUMMARY_PATH="${SHADOW_DIR}/run_summary.json"

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
export SAB_SHADOW_SUMMARY_PATH="${SHADOW_SUMMARY_PATH}"
export SAB_DGC_SHARED_SECRET="${SAB_DGC_SHARED_SECRET:-smoke-shared-secret}"
export BASE_URL
export SMOKE_ADMIN_PRIV
export SMOKE_ADMIN_PUB

rm -f "${DB_PATH}" "${LOG_PATH}"
python3 scripts/orthogonal_safety_loop.py --output-dir "${SHADOW_DIR}" >/dev/null

if [[ ! -f "${SHADOW_SUMMARY_PATH}" ]]; then
  echo "FAIL: missing shadow-loop summary at ${SHADOW_SUMMARY_PATH}"
  exit 1
fi

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
from datetime import datetime, timezone
import json
import os
import subprocess
import sys

import httpx
from nacl.signing import SigningKey

from connectors.sabp_client import SabpClient

base_url = os.environ["BASE_URL"]
admin_priv = os.environ["SMOKE_ADMIN_PRIV"]
admin_pub = os.environ["SMOKE_ADMIN_PUB"]
dgc_secret = os.environ["SAB_DGC_SHARED_SECRET"]

c = SabpClient(base_url)
try:
    health = c.health_check()
    assert health.get("status") == "healthy"

    token_data = c.issue_token("smoke-agent", telos="smoke")
    agent_address = token_data["address"]
    token = token_data["token"]
    now = datetime.now(timezone.utc).isoformat()

    identity_payload = {
        "base_model": "smoke-model",
        "alias": "SMOKE_AGENT",
        "timestamp": now,
        "perceived_role": "smoke-check",
        "self_grade": 0.7,
        "context_hash": "smoke_ctx_001",
        "task_affinity": ["evaluation", "smoke"],
    }
    identity_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "connectors.sabp_cli",
            "--url",
            base_url,
            "--token",
            token,
            "--format",
            "json",
            "identity",
            "--packet",
            json.dumps(identity_payload),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    identity = json.loads(identity_cli.stdout.strip())
    assert identity["status"] == "registered"

    signal_payload = {
        "event_id": "smoke-bootstrap-identity",
        "schema_version": "dgc.v1",
        "timestamp": now,
        "task_id": "smoke-bootstrap",
        "task_type": "evaluation",
        "artifact_id": "smoke-bootstrap-identity",
        "source_alias": "smoke",
        "gate_scores": {"satya": 0.9, "substance": 0.88},
        "collapse_dimensions": {"ritual_ack": 0.2},
        "mission_relevance": 0.9,
    }
    signal_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "connectors.sabp_cli",
            "--url",
            base_url,
            "--token",
            token,
            "--format",
            "json",
            "ingest-dgc",
            "--payload",
            json.dumps(signal_payload),
            "--dgc-secret",
            dgc_secret,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    bootstrap_signal = json.loads(signal_cli.stdout.strip())
    assert bootstrap_signal["event_id"] == "smoke-bootstrap-identity"

    queued = c.submit_post("## Smoke Test\n\nSABP smoke post.")
    queue_id = queued["queue_id"]

    signal_payload = {
        "event_id": f"smoke-{queue_id}",
        "schema_version": "dgc.v1",
        "timestamp": now,
        "task_id": f"smoke-task-{queue_id}",
        "task_type": "evaluation",
        "artifact_id": f"queue-{queue_id}",
        "source_alias": "smoke",
        "gate_scores": {"satya": 0.88, "substance": 0.86},
        "collapse_dimensions": {"ritual_ack": 0.2},
        "mission_relevance": 0.9,
    }
    signal_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "connectors.sabp_cli",
            "--url",
            base_url,
            "--token",
            token,
            "--format",
            "json",
            "ingest-dgc",
            "--payload",
            json.dumps(signal_payload),
            "--dgc-secret",
            dgc_secret,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    signal = json.loads(signal_cli.stdout.strip())
    assert signal["event_id"] == f"smoke-{queue_id}"

    # Queue-first invariant.
    assert c.list_posts() == []

    trust = c.trust_history(agent_address)
    assert trust["latest"]["signal_event_id"] == f"smoke-{queue_id}"
    landscape = c.convergence_landscape()
    assert any(n["agent_address"] == agent_address for n in landscape["nodes"])

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

        admin_headers = {"Authorization": f"Bearer {admin_jwt}"}
        r = raw.get("/admin/convergence/anti-gaming/scan", headers=admin_headers)
        r.raise_for_status()
        assert "summary" in r.json()

        r = raw.post(
            f"/admin/convergence/clawback/smoke-{queue_id}",
            headers=admin_headers,
            json={"reason": "smoke anti-gaming clawback", "penalty": 0.2},
        )
        r.raise_for_status()
        assert r.json()["status"] == "clawback_applied"

        r = raw.post(
            f"/admin/convergence/override/smoke-{queue_id}",
            headers=admin_headers,
            json={"reason": "smoke override reset", "trust_adjustment": 0.0},
        )
        r.raise_for_status()
        assert r.json()["status"] == "trust_override_applied"

        r = raw.post(
            f"/admin/convergence/outcomes/smoke-{queue_id}",
            headers=admin_headers,
            json={"outcome_type": "tests", "status": "pass", "evidence": {"suite": "smoke"}},
        )
        r.raise_for_status()
        assert r.json()["outcome"]["event_id"] == f"smoke-{queue_id}"

        r = raw.post(
            "/admin/convergence/darwin/run",
            headers=admin_headers,
            json={"dry_run": True, "reason": "smoke cycle", "run_validation": False},
        )
        r.raise_for_status()
        assert "run_id" in r.json()

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
