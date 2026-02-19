#!/usr/bin/env python3
"""
Enforce claim promotion thresholds across repo claim packets.

Usage:
  python3 scripts/enforce_claim_promotions.py
  python3 scripts/enforce_claim_promotions.py --require-stage
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agora.claim_promotion import run_promotion_enforcement


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce claim-promotion stage thresholds in repo.")
    parser.add_argument("--nodes-root", default="nodes", help="Nodes root directory to scan")
    parser.add_argument(
        "--require-stage",
        action="store_true",
        help="Fail when a claim packet lacks requested_stage/requested_stages",
    )
    parser.add_argument(
        "--fail-on-no-claims",
        action="store_true",
        help="Fail when no claim packet JSON files exist",
    )
    args = parser.parse_args()

    report = run_promotion_enforcement(
        nodes_root=Path(args.nodes_root),
        require_stage=bool(args.require_stage),
        fail_on_no_claims=bool(args.fail_on_no_claims),
    )
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

