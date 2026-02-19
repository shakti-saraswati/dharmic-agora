#!/usr/bin/env python3
"""
High-level claim creator wrapper.

This wraps scaffold_claim_packet.py with minimal required inputs and optional
interactive prompts so operators don't need to remember full flags.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]


def _available_nodes() -> List[str]:
    root = REPO_ROOT / "nodes" / "anchors"
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def _prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value if value else default


def main() -> int:
    nodes = _available_nodes()
    parser = argparse.ArgumentParser(description="Create a claim packet with strict-governance defaults.")
    parser.add_argument("--node", default="", help=f"Anchor node id. Options: {', '.join(nodes)}")
    parser.add_argument("--title", default="", help="Claim title")
    parser.add_argument("--summary", default="", help="Optional summary")
    parser.add_argument("--stage", default="paper_internal_draft", help="Requested stage")
    parser.add_argument("--claim-id", default="", help="Optional explicit claim id (auto if omitted)")
    parser.add_argument("--cross-node", action="append", default=[], help="Optional non-adjacent witness node")
    parser.add_argument("--artifact-ref", action="append", default=[], help="Optional artifact ref path")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--dry-run", action="store_true", help="Print output only")
    args = parser.parse_args()

    node = args.node.strip()
    title = args.title.strip()
    summary = args.summary.strip()

    interactive = sys.stdin.isatty()
    if not node and interactive:
        if not nodes:
            raise SystemExit("No nodes found under nodes/anchors/")
        print("Available nodes:")
        for idx, item in enumerate(nodes, start=1):
            print(f"  {idx}. {item}")
        node = _prompt("Node id", nodes[0])

    if not title and interactive:
        title = _prompt("Claim title")

    if not summary and interactive:
        summary = _prompt("Summary (optional)", "")

    if not node:
        raise SystemExit("Missing --node")
    if node not in nodes:
        raise SystemExit(f"Unknown node '{node}'. Valid options: {nodes}")
    if not title:
        raise SystemExit("Missing --title")

    cmd = [
        sys.executable,
        "scripts/scaffold_claim_packet.py",
        "--node",
        node,
        "--title",
        title,
        "--stage",
        args.stage,
    ]
    if summary:
        cmd.extend(["--summary", summary])
    if args.claim_id.strip():
        cmd.extend(["--claim-id", args.claim_id.strip()])
    for cross_node in args.cross_node:
        cmd.extend(["--cross-node", cross_node])
    for artifact_ref in args.artifact_ref:
        cmd.extend(["--artifact-ref", artifact_ref])
    if args.force:
        cmd.append("--force")
    if args.dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        return proc.returncode

    # Friendly next-step hint.
    try:
        payload = json.loads(proc.stdout.strip())
    except Exception:
        return 0
    claim_path = payload.get("claim_path", "")
    stage = payload.get("requested_stage", args.stage)
    print(
        json.dumps(
            {
                "status": "next",
                "claim_path": claim_path,
                "verify": (
                    f"python3 scripts/validate_claim_packet.py --claim {claim_path} --stage {stage}"
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

