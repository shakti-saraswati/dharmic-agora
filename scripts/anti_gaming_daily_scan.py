#!/usr/bin/env python3
"""
Daily anti-gaming scan for SAB convergence signals.

Usage:
  python3 scripts/anti_gaming_daily_scan.py
  python3 scripts/anti_gaming_daily_scan.py --limit 1000 --fail-threshold 10
"""

from __future__ import annotations

import argparse
import json

from agora.config import get_db_path
from agora.convergence import ConvergenceStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run anti-gaming diagnostics over recent convergence signals.")
    parser.add_argument("--limit", type=int, default=500, help="Number of recent trust events to scan")
    parser.add_argument(
        "--fail-threshold",
        type=int,
        default=-1,
        help="Exit non-zero when suspicious_count is greater than this value (-1 disables)",
    )
    args = parser.parse_args()

    store = ConvergenceStore(get_db_path())
    report = store.anti_gaming_report(limit=max(50, args.limit))
    print(json.dumps(report, sort_keys=True))

    suspicious = int(report.get("summary", {}).get("suspicious_count", 0))
    if args.fail_threshold >= 0 and suspicious > args.fail_threshold:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
