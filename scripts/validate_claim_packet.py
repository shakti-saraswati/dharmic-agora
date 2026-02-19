#!/usr/bin/env python3
"""
Validate a SAB claim packet against stage-specific promotion thresholds.

Usage:
  python3 scripts/validate_claim_packet.py --claim path/to/claim.json --stage canon_propagation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agora.node_governance import (
    STAGE_CANON,
    STAGE_PAPER_EXTERNAL,
    STAGE_PAPER_INTERNAL,
    STAGE_VENTURE_EXTERNAL,
    STAGE_VENTURE_PROPOSAL,
    evaluate_claim_for_stage,
)


def _load_claim(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"claim file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in claim file: {path} ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError("claim packet must be a JSON object")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate claim packet promotion thresholds.")
    parser.add_argument("--claim", required=True, help="Path to claim JSON packet")
    parser.add_argument(
        "--stage",
        required=True,
        choices=[
            STAGE_PAPER_INTERNAL,
            STAGE_PAPER_EXTERNAL,
            STAGE_CANON,
            STAGE_VENTURE_PROPOSAL,
            STAGE_VENTURE_EXTERNAL,
        ],
        help="Target governance stage",
    )
    args = parser.parse_args()

    try:
        claim = _load_claim(Path(args.claim))
    except ValueError as exc:
        print(json.dumps({"passed": False, "error": str(exc)}))
        return 2

    result = evaluate_claim_for_stage(claim, args.stage)
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
