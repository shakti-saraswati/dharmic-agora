#!/usr/bin/env python3
"""
Anomaly detection for coordination risks.

Consumes enforcement state and systemic monitor outputs to emit alerts.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from agora.security import systemic_monitor
except ImportError:
    import systemic_monitor

POLICY_PATH = Path(__file__).parent / "policy" / "anomaly_detection.yaml"
ALERTS_LOG = Path(__file__).parent.parent / "logs" / "alerts.jsonl"
ENFORCEMENT_STATE = Path(__file__).parent.parent / "logs" / "enforcement" / "enforcement_state.json"
INTERACTION_LOG = Path(__file__).parent.parent / "logs" / "interaction_events.jsonl"


@dataclass
class Alert:
    timestamp: str
    severity: str
    reason: str
    details: Dict[str, Any]


def _load_policy() -> dict:
    if POLICY_PATH.exists():
        return yaml.safe_load(POLICY_PATH.read_text()) or {}
    return {}


def _load_enforcement() -> dict:
    if not ENFORCEMENT_STATE.exists():
        return {}
    return json.loads(ENFORCEMENT_STATE.read_text())


def detect_anomalies(events_path: Optional[Path] = None) -> List[Alert]:
    policy = _load_policy()
    thresholds = policy.get("thresholds", {})

    alerts: List[Alert] = []
    now = datetime.now(timezone.utc).isoformat()

    # Enforcement failures
    enforcement = _load_enforcement()
    failures = enforcement.get("consecutive_failures", 0)
    rejections = 0
    for p in enforcement.get("proposals", []):
        if not p.get("success", True):
            rejections += 1

    if failures >= thresholds.get("max_consecutive_failures", 3):
        alerts.append(Alert(
            timestamp=now,
            severity="high",
            reason="consecutive_failures",
            details={"count": failures},
        ))

    if rejections >= thresholds.get("max_daily_rejections", 5):
        alerts.append(Alert(
            timestamp=now,
            severity="medium",
            reason="daily_rejections",
            details={"count": rejections},
        ))

    # Systemic risk
    events_path = events_path or INTERACTION_LOG
    events = systemic_monitor.load_events(events_path)
    policy_risk = systemic_monitor.load_policy(None)
    report = systemic_monitor.evaluate(events, policy_risk)
    if len(report.flags) >= thresholds.get("max_systemic_flags", 2):
        alerts.append(Alert(
            timestamp=now,
            severity="high",
            reason="systemic_risk",
            details={"flags": report.flags, "status": report.status},
        ))

    return alerts


def write_alerts(alerts: List[Alert]) -> None:
    ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERTS_LOG, "a", encoding="utf-8") as f:
        for alert in alerts:
            f.write(json.dumps(asdict(alert)) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Anomaly detector")
    parser.add_argument("--events", help="Path to interaction events JSONL")
    args = parser.parse_args()

    alerts = detect_anomalies(Path(args.events) if args.events else None)
    write_alerts(alerts)
    print(json.dumps([asdict(a) for a in alerts], indent=2))
    if alerts:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
