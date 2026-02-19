#!/usr/bin/env python3
"""Validation loop runner for SAB / dharmic-agora.

Goal
- Make "verify output, not code" mechanical.
- Run a local validation suite and emit a single PASS/FAIL with artifacts.

This is intentionally simple and dependency-free.

Usage
  python3 scripts/validation_loop.py --suite unit
  python3 scripts/validation_loop.py --suite integration

Exit codes
  0 = PASS
  1 = FAIL
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RunResult:
    name: str
    ok: bool
    status: str  # PASS|FAIL|SKIP
    cmd: List[str]
    returncode: int
    seconds: float
    stdout_path: str
    stderr_path: str


def _run(cmd: List[str], out_dir: Path, name: str, env: Dict[str, str]) -> RunResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = out_dir / f"{name}.stdout.txt"
    stderr_path = out_dir / f"{name}.stderr.txt"

    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    except FileNotFoundError as e:
        # Surface as a clean failure with artifacts.
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(e), encoding="utf-8")
        return RunResult(
            name=name,
            ok=False,
            status="FAIL",
            cmd=cmd,
            returncode=127,
            seconds=0.0,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
        )
    dt = time.time() - t0

    stdout_path.write_text(p.stdout or "", encoding="utf-8")
    stderr_path.write_text(p.stderr or "", encoding="utf-8")

    ok = (p.returncode == 0)
    return RunResult(
        name=name,
        ok=ok,
        status="PASS" if ok else "FAIL",
        cmd=cmd,
        returncode=p.returncode,
        seconds=round(dt, 3),
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["unit", "integration", "all"], default="unit")
    ap.add_argument("--out", default="validation_artifacts")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]

    # Some deployments mount repos read-only; write artifacts to scratch by default.
    out_root = Path(os.getenv("SAB_VALIDATION_OUT", "/tmp/sab_validation_artifacts"))
    out_dir = out_root / "dharmic-agora" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    env = dict(os.environ)
    # Avoid __pycache__ write failures in constrained environments.
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    results: List[RunResult] = []

    # Always run syntax check first (fast fail).
    # Use AST parsing (no __pycache__ writes).
    syntax_cmd = [sys.executable, "-c", (
        "import ast, pathlib; "
        "root=pathlib.Path('agora'); "
        "files=[p for p in root.rglob('*.py')]; "
        "[ast.parse(p.read_text()) for p in files]; "
        "print('syntax_ok', len(files))"
    )]
    results.append(_run(syntax_cmd, out_dir, "syntax", env))
    results.append(
        _run(
            [sys.executable, "scripts/enforce_claim_promotions.py"],
            out_dir,
            "claim_promotion_enforcement",
            env,
        )
    )

    if args.suite in ("unit", "all"):
        if shutil.which("pytest"):
            results.append(_run(["pytest", "-q", "agora/tests", "-k", "not integration"], out_dir, "pytest_unit", env))
        else:
            # If pytest isn't installed in this runtime, mark as skipped.
            skip_path = out_dir / "pytest_unit.stderr.txt"
            skip_path.parent.mkdir(parents=True, exist_ok=True)
            skip_path.write_text("SKIPPED: pytest not installed in this runtime\n", encoding="utf-8")
            results.append(
                RunResult(
                    name="pytest_unit",
                    ok=True,
                    status="SKIP",
                    cmd=["pytest"],
                    returncode=0,
                    seconds=0.0,
                    stdout_path=str(out_dir / "pytest_unit.stdout.txt"),
                    stderr_path=str(skip_path),
                )
            )

    if args.suite in ("integration", "all"):
        results.append(
            _run([sys.executable, "scripts/integration_test.py"], out_dir, "integration_test", env)
        )

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "repo_root": str(repo_root),
        "results": [r.__dict__ for r in results],
        "overall": "PASS" if all(r.ok for r in results) else "FAIL",
    }

    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"overall": report["overall"], "artifacts": str(out_dir)}, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
