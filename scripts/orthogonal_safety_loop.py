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


def run_loop(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

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
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "alerting" if high_alerts else "stable",
        "alert_count": len(alerts),
        "high_alert_count": len(high_alerts),
        "acp_path": str(acp_path),
        "alerts_path": str(alerts_path),
        "report_path": str(report_path),
    }

    summary_path = output_dir / "run_summary.json"
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
