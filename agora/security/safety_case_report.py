#!/usr/bin/env python3
"""
Safety case report generator.

Combines the static safety case template with live ACP/red-team evidence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dataclasses import asdict
from swarm.compliance_profile import generate_profile

TEMPLATE_PATH = Path(__file__).parent.parent / "docs" / "SAFETY_CASE_OACP_DGC.md"
REPORT_PATH = Path(__file__).parent.parent / "docs" / "SAFETY_CASE_OACP_DGC_REPORT.md"


def generate_report() -> str:
    template = TEMPLATE_PATH.read_text() if TEMPLATE_PATH.exists() else ""
    profile = generate_profile()

    evidence_block = "\n## 9) Current Evidence Snapshot\n\n"
    evidence_block += f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
    evidence_block += "```json\n"
    evidence_block += json.dumps(asdict(profile), indent=2)
    evidence_block += "\n```\n"

    return template + "\n\n" + evidence_block


def main() -> None:
    parser = argparse.ArgumentParser(description="Safety case report generator")
    parser.add_argument("--output", help="Output path for report")
    args = parser.parse_args()

    report = generate_report()
    out = Path(args.output) if args.output else REPORT_PATH
    out.write_text(report)
    print(f"Report written to {out}")


if __name__ == "__main__":
    main()
