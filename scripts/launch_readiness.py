#!/usr/bin/env python3
"""
Launch readiness scorer for SAB / Dharmic Agora.

It combines:
1) Runtime launch gates (weighted, 0-100), and
2) Structural debt penalties (subtract from runtime score)

Output includes a single industry-readiness score and evidence.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient
from nacl.signing import SigningKey

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class RuntimeCheck:
    name: str
    weight: int
    ok: bool
    status: str
    evidence: str
    detail: Dict[str, Any]


@dataclass
class DebtPenalty:
    name: str
    penalty: int
    status: str
    evidence: str
    detail: Dict[str, Any]


def _status(ok: bool) -> str:
    return "VERIFIED" if ok else "MISSING"


def _purge_agora_modules() -> None:
    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]


def _run_runtime_checks(repo_root: Path) -> List[RuntimeCheck]:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.environ["SAB_DB_PATH"] = f"/tmp/sab_launch_readiness_{ts}.db"
    os.environ["SAB_JWT_SECRET"] = f"/tmp/sab_launch_readiness_{ts}.jwt"
    os.environ["ENFORCE_HTTPS"] = "true"
    os.environ["SAB_FEDERATION_SHARED_SECRET"] = "readiness-secret"
    os.environ["SAB_CORS_ORIGINS"] = "https://agora.example,http://localhost:3000"
    os.environ["SAB_ENV"] = "development"

    _purge_agora_modules()
    api_server = importlib.import_module("agora.api_server")
    client = TestClient(api_server.app)

    checks: List[RuntimeCheck] = []

    def add(name: str, weight: int, ok: bool, evidence: str, detail: Dict[str, Any]) -> None:
        checks.append(
            RuntimeCheck(
                name=name,
                weight=weight,
                ok=ok,
                status=_status(ok),
                evidence=evidence,
                detail=detail,
            )
        )

    # 1) HTTPS enforcement
    r = client.get("/health")
    add(
        "https_blocks_plain_http",
        15,
        r.status_code == 400 and r.json().get("error") == "HTTPS required",
        "GET /health with ENFORCE_HTTPS=true and no x-forwarded-proto",
        {"status_code": r.status_code, "body": r.json() if "application/json" in r.headers.get("content-type", "") else r.text},
    )

    r = client.get("/health", headers={"x-forwarded-proto": "https"})
    add(
        "https_allows_forwarded_https",
        10,
        r.status_code == 200,
        "GET /health with x-forwarded-proto=https",
        {"status_code": r.status_code},
    )

    https_headers = {"x-forwarded-proto": "https"}

    # 2) Auth flow
    sk = SigningKey.generate()
    pubkey = sk.verify_key.encode().hex()
    reg = client.post("/auth/register", json={"name": "readiness-agent", "pubkey": pubkey, "telos": "launch-readiness"}, headers=https_headers)
    addr = reg.json().get("address") if reg.status_code == 200 else None
    challenge = None
    verify = None
    if addr:
        challenge = client.get("/auth/challenge", params={"address": addr}, headers=https_headers)
        if challenge.status_code == 200:
            ch_hex = challenge.json()["challenge"]
            sig_hex = sk.sign(bytes.fromhex(ch_hex)).signature.hex()
            verify = client.post("/auth/verify", json={"address": addr, "signature": sig_hex}, headers=https_headers)

    auth_ok = (
        reg.status_code == 200
        and challenge is not None
        and challenge.status_code == 200
        and verify is not None
        and verify.status_code == 200
        and bool(verify.json().get("token"))
    )
    add(
        "auth_register_challenge_verify_flow",
        15,
        auth_ok,
        "POST /auth/register -> GET /auth/challenge -> POST /auth/verify",
        {
            "register_status": reg.status_code,
            "challenge_status": challenge.status_code if challenge else None,
            "verify_status": verify.status_code if verify else None,
        },
    )

    # 3) Core content gates
    gates = client.get("/gates", headers=https_headers)
    add("gates_endpoint", 8, gates.status_code == 200, "GET /gates", {"status_code": gates.status_code})

    ge = client.post("/gates/evaluate", params={"content": "Evidence-backed structured post.", "agent_telos": "safety"}, headers=https_headers)
    add(
        "gates_evaluate_endpoint",
        8,
        ge.status_code == 200 and isinstance(ge.json().get("gate_result"), dict),
        "POST /gates/evaluate",
        {"status_code": ge.status_code},
    )

    ke = client.post("/kernel/evaluate", params={"content": "Deployment method with tests and logs.", "agent_telos": "safety"}, headers=https_headers)
    add(
        "kernel_evaluate_endpoint",
        12,
        ke.status_code == 200 and isinstance(ke.json().get("kernel"), dict),
        "POST /kernel/evaluate",
        {"status_code": ke.status_code},
    )

    witness = client.get("/witness", headers=https_headers)
    add(
        "witness_endpoint",
        5,
        witness.status_code == 200 and isinstance(witness.json(), list),
        "GET /witness",
        {"status_code": witness.status_code},
    )

    # 4) Federation auth behavior
    fed_no_hdr = client.get("/api/federation/health", headers=https_headers)
    add(
        "federation_secret_enforced",
        10,
        fed_no_hdr.status_code == 401,
        "GET /api/federation/health without X-SAB-Federation-Secret (secret configured)",
        {"status_code": fed_no_hdr.status_code},
    )

    fed_ok = client.get(
        "/api/federation/health",
        headers={**https_headers, "X-SAB-Federation-Secret": "readiness-secret"},
    )
    add(
        "federation_health_with_secret",
        7,
        fed_ok.status_code == 200,
        "GET /api/federation/health with valid federation secret",
        {"status_code": fed_ok.status_code},
    )

    # 5) CORS behavior
    cors_allowed = client.options(
        "/gates",
        headers={
            **https_headers,
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    add(
        "cors_allowed_origin",
        5,
        cors_allowed.status_code == 200 and cors_allowed.headers.get("access-control-allow-origin") == "http://localhost:3000",
        "OPTIONS /gates with allowed origin",
        {"status_code": cors_allowed.status_code, "acao": cors_allowed.headers.get("access-control-allow-origin")},
    )

    cors_blocked = client.options(
        "/gates",
        headers={
            **https_headers,
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    add(
        "cors_blocks_disallowed_origin",
        5,
        cors_blocked.status_code == 400 and cors_blocked.headers.get("access-control-allow-origin") is None,
        "OPTIONS /gates with disallowed origin",
        {"status_code": cors_blocked.status_code, "acao": cors_blocked.headers.get("access-control-allow-origin")},
    )

    return checks


def _run_debt_penalties(repo_root: Path) -> List[DebtPenalty]:
    api_server = (repo_root / "agora" / "api_server.py").read_text(encoding="utf-8")
    gates_file = (repo_root / "agora" / "gates.py").read_text(encoding="utf-8")
    system_md = (repo_root / "SYSTEM.md").read_text(encoding="utf-8") if (repo_root / "SYSTEM.md").exists() else ""

    penalties: List[DebtPenalty] = []

    def add(name: str, penalty: int, triggered: bool, evidence: str, detail: Dict[str, Any]) -> None:
        penalties.append(
            DebtPenalty(
                name=name,
                penalty=penalty if triggered else 0,
                status="PARTIAL" if triggered else "VERIFIED",
                evidence=evidence,
                detail=detail,
            )
        )

    # Drift: legacy 17-gate scaffolding + orthogonal runtime gate path coexist.
    drift = "class GateKeeper" in api_server and "OrthogonalGates().evaluate" in api_server and "class GateProtocol" in gates_file
    add(
        "dual_gate_system_drift",
        10,
        drift,
        "api_server.py + gates.py contain overlapping gate systems",
        {"triggered": drift},
    )

    # Monolith risk: very large API server module.
    line_count = api_server.count("\n") + 1
    monolith = line_count > 2000
    add(
        "api_server_monolith_size",
        10,
        monolith,
        "api_server.py line count",
        {"line_count": line_count, "threshold": 2000},
    )

    # Stale architecture doc references legacy src/* layout.
    stale_docs = bool(re.search(r"`src/", system_md))
    add(
        "system_doc_drift",
        5,
        stale_docs,
        "SYSTEM.md references legacy src/* layout",
        {"triggered": stale_docs},
    )

    return penalties


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute SAB launch readiness score with evidence.")
    parser.add_argument("--target", type=int, default=70, help="Target industry readiness score")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: NORTH_STAR/launch_readiness_<timestamp>.json)",
    )
    args = parser.parse_args()

    repo_root = REPO_ROOT
    runtime_checks = _run_runtime_checks(repo_root)
    debt_penalties = _run_debt_penalties(repo_root)

    base_runtime_score = sum(c.weight for c in runtime_checks if c.ok)
    total_penalty = sum(p.penalty for p in debt_penalties)
    industry_readiness_score = max(0, base_runtime_score - total_penalty)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_path = args.out or (repo_root / "NORTH_STAR" / f"launch_readiness_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": ts,
        "target_score": args.target,
        "base_runtime_score": base_runtime_score,
        "technical_debt_penalty": total_penalty,
        "industry_readiness_score": industry_readiness_score,
        "meets_target": industry_readiness_score >= args.target,
        "runtime_checks": [asdict(c) for c in runtime_checks],
        "debt_penalties": [asdict(p) for p in debt_penalties],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"launch_readiness_score={industry_readiness_score}")
    print(f"base_runtime_score={base_runtime_score}")
    print(f"technical_debt_penalty={total_penalty}")
    print(f"meets_target={payload['meets_target']}")
    print(f"report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
