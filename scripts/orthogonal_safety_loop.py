#!/usr/bin/env python3
"""
SAB Shadow Loop

Orthogonal reliability/security cycle:
1) Build ACP profile snapshot
2) Run anomaly detection
3) Generate safety case report with live evidence
4) Emit one summary JSON for quick triage
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agora.security.anomaly_detection import detect_anomalies
from agora.security.compliance_profile import ACPProfile, generate_profile
from agora.security.safety_case_report import generate_report


def _load_previous_summary(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _trend_deltas(profile: ACPProfile, alerts: list, previous_summary: dict | None) -> dict:
    current_gate = asdict(profile.gate_stats)
    if not previous_summary:
        return {
            "baseline": True,
            "alert_count_delta": 0,
            "high_alert_count_delta": 0,
            "gate_runs_delta": 0,
            "gate_passed_delta": 0,
            "gate_failed_delta": 0,
            "gate_warned_delta": 0,
        }

    prev_gate = previous_summary.get("gate_stats", {})
    prev_alert_count = int(previous_summary.get("alert_count", 0))
    prev_high_alert_count = int(previous_summary.get("high_alert_count", 0))

    current_high = len([a for a in alerts if a.severity.lower() == "high"])
    return {
        "baseline": False,
        "alert_count_delta": len(alerts) - prev_alert_count,
        "high_alert_count_delta": current_high - prev_high_alert_count,
        "gate_runs_delta": int(current_gate.get("total_runs", 0)) - int(prev_gate.get("total_runs", 0) or 0),
        "gate_passed_delta": int(current_gate.get("gates_passed", 0)) - int(prev_gate.get("gates_passed", 0) or 0),
        "gate_failed_delta": int(current_gate.get("gates_failed", 0)) - int(prev_gate.get("gates_failed", 0) or 0),
        "gate_warned_delta": int(current_gate.get("gates_warned", 0)) - int(prev_gate.get("gates_warned", 0) or 0),
    }


def run_loop(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "run_summary.json"
    previous_summary = _load_previous_summary(summary_path)

    profile: ACPProfile = generate_profile()
    acp_path = output_dir / "acp_profile.json"
    acp_path.write_text(json.dumps(asdict(profile), indent=2))

    alerts = detect_anomalies()
    alerts_path = output_dir / "anomaly_alerts.json"
    alerts_path.write_text(json.dumps([asdict(a) for a in alerts], indent=2))

    report = generate_report(profile=profile)
    report_path = output_dir / "safety_case_report.md"
    report_path.write_text(report)

    high_alerts = [a for a in alerts if a.severity.lower() == "high"]
    gate_stats = asdict(profile.gate_stats)
    trend = _trend_deltas(profile, alerts, previous_summary)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "alerting" if high_alerts else "stable",
        "alert_count": len(alerts),
        "high_alert_count": len(high_alerts),
        "gate_stats": gate_stats,
        "trend": trend,
        "acp_path": str(acp_path),
        "alerts_path": str(alerts_path),
        "report_path": str(report_path),
    }

    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SAB Shadow Loop")
    parser.add_argument(
        "--output-dir",
        default="agora/logs/shadow_loop",
        help="Directory for ACP/alerts/report outputs",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when high-severity alerts are present",
    )
    args = parser.parse_args()

    summary = run_loop(Path(args.output_dir))
    print(json.dumps(summary, indent=2))
    if args.strict and summary["high_alert_count"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
