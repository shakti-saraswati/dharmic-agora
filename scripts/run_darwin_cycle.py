#!/usr/bin/env python3
"""
Run one Darwin cycle directly against the SAB convergence store.

Usage:
  python3 scripts/run_darwin_cycle.py
  python3 scripts/run_darwin_cycle.py --apply --reason "nightly tuning"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from agora.config import get_db_path
    from agora.convergence import ConvergenceStore
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agora.config import get_db_path
    from agora.convergence import ConvergenceStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Darwin convergence policy cycle.")
    parser.add_argument("--reviewer", default="local_darwin_runner")
    parser.add_argument("--reason", default="manual_darwin_cycle")
    parser.add_argument("--apply", action="store_true", help="Persist candidate policy when improved")
    parser.add_argument(
        "--run-validation",
        action="store_true",
        help="Run expensive validation commands (pytest + smoke) as part of cycle",
    )
    args = parser.parse_args()

    store = ConvergenceStore(get_db_path())
    result = store.run_darwin_cycle(
        reviewer=args.reviewer,
        reason=args.reason,
        dry_run=not args.apply,
        run_validation=args.run_validation,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
