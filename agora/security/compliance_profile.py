#!/usr/bin/env python3
"""
Attested Compliance Profile (ACP) generator.

Summarizes gate performance, red-team outcomes, systemic risk, and enforcement state.
"""

from __future__ import annotations

import argparse
import hmac
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from agora.security import systemic_monitor
    from agora.security.skill_registry import verify_registry
    from agora.security.token_registry import TokenRegistry
except ImportError:
    import systemic_monitor
    from skill_registry import verify_registry
    from token_registry import TokenRegistry

EVIDENCE_DIR = Path(__file__).parent.parent / "evidence"
REDTEAM_DIRS = [
    Path(__file__).parent.parent / "logs" / "redteam",
    EVIDENCE_DIR / "redteam",
]
INTERACTION_LOG = Path(__file__).parent.parent / "logs" / "interaction_events.jsonl"
ENFORCEMENT_STATE = Path(__file__).parent.parent / "logs" / "enforcement" / "enforcement_state.json"
ACP_PATH = Path(__file__).parent.parent / "logs" / "acp_profile.json"


@dataclass
class GateStats:
    total_runs: int
    gates_passed: int
    gates_failed: int
    gates_warned: int


@dataclass
class ACPProfile:
    timestamp: str
    gate_stats: GateStats
    redteam_summary: Dict[str, Any]
    systemic_risk: Dict[str, Any]
    enforcement: Dict[str, Any]
    skill_registry: Dict[str, Any]
    token_registry: Dict[str, Any]
    signature: Optional[str] = None


def _collect_gate_stats() -> GateStats:
    total_runs = 0
    passed = failed = warned = 0
    for result in EVIDENCE_DIR.glob("*/gate_results.json"):
        data = json.loads(result.read_text())
        total_runs += 1
        passed += data.get("gates_passed", 0)
        failed += data.get("gates_failed", 0)
        warned += data.get("gates_warned", 0)
    return GateStats(total_runs=total_runs, gates_passed=passed, gates_failed=failed, gates_warned=warned)


def _latest_redteam() -> Dict[str, Any]:
    reports = []
    for directory in REDTEAM_DIRS:
        if not directory.exists():
            continue
        reports.extend(directory.glob("ab_test_*.json"))
    if not reports:
        return {"status": "missing"}
    latest = max(reports, key=lambda p: p.stat().st_mtime)
    data = json.loads(latest.read_text())
    return {"status": "ok", "summary": data.get("summary", {}), "path": str(latest)}


def _systemic_snapshot() -> Dict[str, Any]:
    events = systemic_monitor.load_events(INTERACTION_LOG)
    policy = systemic_monitor.load_policy(None)
    report = systemic_monitor.evaluate(events, policy)
    return {"metrics": asdict(report.metrics), "flags": report.flags, "status": report.status}


def _enforcement_state() -> Dict[str, Any]:
    if not ENFORCEMENT_STATE.exists():
        return {"status": "missing"}
    return json.loads(ENFORCEMENT_STATE.read_text())


def _token_stats() -> Dict[str, Any]:
    registry = TokenRegistry()
    tokens = registry.list_tokens()
    active = registry.list_tokens(active_only=True)
    return {
        "total": len(tokens),
        "active": len(active),
    }


def _sign_profile(profile: dict) -> Optional[str]:
    key = os.getenv("ACP_SIGNING_KEY")
    if not key:
        return None
    payload = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def generate_profile() -> ACPProfile:
    gate_stats = _collect_gate_stats()
    redteam_summary = _latest_redteam()
    systemic_risk = _systemic_snapshot()
    enforcement = _enforcement_state()
    skill_check = verify_registry()
    token_stats = _token_stats()

    profile = ACPProfile(
        timestamp=datetime.now(timezone.utc).isoformat(),
        gate_stats=gate_stats,
        redteam_summary=redteam_summary,
        systemic_risk=systemic_risk,
        enforcement=enforcement,
        skill_registry=skill_check.__dict__,
        token_registry=token_stats,
    )

    raw = asdict(profile)
    signature = _sign_profile(raw)
    profile.signature = signature
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ACP profile")
    parser.add_argument("--output", help="Output file (default logs/acp_profile.json)")
    args = parser.parse_args()

    profile = generate_profile()
    out = Path(args.output) if args.output else ACP_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(asdict(profile), indent=2))
    print(f"ACP profile written to {out}")


if __name__ == "__main__":
    main()
