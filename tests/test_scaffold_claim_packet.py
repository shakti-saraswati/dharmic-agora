from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scaffold_claim_packet_dry_run_succeeds() -> None:
    cmd = [
        sys.executable,
        "scripts/scaffold_claim_packet.py",
        "--node",
        "anchor-03-ml-intelligence-engineering",
        "--claim-id",
        "claim-test-dry-run-scaffold-v1",
        "--title",
        "Dry run scaffold claim",
        "--stage",
        "paper_internal_draft",
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload["status"] == "ok"
    assert payload["dry_run"] is True
    assert payload["requested_stage"] == "paper_internal_draft"
    assert payload["claim_path"].endswith("claim-test-dry-run-scaffold-v1.json")


def test_scaffold_claim_packet_rejects_adjacent_cross_node() -> None:
    cmd = [
        sys.executable,
        "scripts/scaffold_claim_packet.py",
        "--node",
        "anchor-03-ml-intelligence-engineering",
        "--claim-id",
        "claim-test-invalid-cross-node-v1",
        "--title",
        "Invalid cross-node claim",
        "--cross-node",
        "anchor-04-complex-systems-cybernetics",
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode != 0
    combined = (proc.stdout + proc.stderr).lower()
    assert "invalid" in combined or "must be non-adjacent" in combined

