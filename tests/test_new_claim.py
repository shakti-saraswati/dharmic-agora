from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_new_claim_dry_run_non_interactive() -> None:
    cmd = [
        sys.executable,
        "scripts/new_claim.py",
        "--node",
        "anchor-03-ml-intelligence-engineering",
        "--title",
        "New claim wrapper dry run",
        "--stage",
        "paper_internal_draft",
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    assert len(lines) >= 1
    first = json.loads(lines[0])
    assert first["status"] == "ok"
    assert first["requested_stage"] == "paper_internal_draft"

