#!/usr/bin/env python3
"""
Adapter: Agentic Coding Swarm "Canyon Pattern" -> SABP submission.

Reads a session directory like:
  ~/.agentic_coding/session_<id>/
    trigger_prompt.txt
    yolo_code.py
    fixed_code.py
    verification_report.md
    review_discussion.md

Then submits a single SABP post containing the key artifacts.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    # Preferred: module execution (`python -m connectors.canyon_to_sabp`).
    from .sabp_client import SabpAuth, SabpClient
except ImportError:  # pragma: no cover
    # Also support script execution (`python connectors/canyon_to_sabp.py`).
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from connectors.sabp_client import SabpAuth, SabpClient  # type: ignore


def _read_if_exists(p: Path) -> str | None:
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def build_markdown(session_dir: Path) -> str:
    sid = session_dir.name.replace("session_", "")

    trigger = _read_if_exists(session_dir / "trigger_prompt.txt")
    yolo = _read_if_exists(session_dir / "yolo_code.py")
    fixed = _read_if_exists(session_dir / "fixed_code.py")
    report = _read_if_exists(session_dir / "verification_report.md")
    review = _read_if_exists(session_dir / "review_discussion.md")

    final_code = fixed or yolo or ""

    parts: list[str] = []
    parts.append(f"# Canyon Session {sid}")
    parts.append("")
    parts.append(f"- Source: `{session_dir}`")
    parts.append("")

    if trigger:
        parts.append("## Trigger Prompt")
        parts.append("```")
        parts.append(trigger.strip())
        parts.append("```")
        parts.append("")

    if final_code:
        parts.append("## Final Code")
        parts.append("```python")
        parts.append(final_code.strip())
        parts.append("```")
        parts.append("")

    if report:
        parts.append("## Verification Report")
        parts.append("```")
        parts.append(report.strip())
        parts.append("```")
        parts.append("")

    if review:
        parts.append("## Review Discussion")
        parts.append(review.strip())
        parts.append("")

    parts.append("## Artifact List")
    for f in sorted(session_dir.glob("*")):
        if f.is_file():
            parts.append(f"- `{f.name}`")

    return "\n".join(parts).strip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Submit a Canyon session to SABP")
    ap.add_argument("--session-dir", required=True, help="Path to session_<id> directory")
    ap.add_argument("--url", default=os.getenv("SABP_URL", "http://localhost:8000"))
    ap.add_argument("--token", default=os.getenv("SABP_TOKEN"))
    ap.add_argument("--name", default="canyon-adapter", help="If --token is missing, issue a Tier-1 token with this name")
    ap.add_argument("--telos", default="coding", help="If issuing a token, use this telos")
    args = ap.parse_args()

    auth = SabpAuth(bearer_token=args.token)
    c = SabpClient(args.url, auth=auth)
    try:
        if not c.auth.bearer_token:
            c.issue_token(args.name, telos=args.telos)

        content = build_markdown(Path(args.session_dir).expanduser())
        out = c.submit_post(content)
        print(out)
    finally:
        c.close()


if __name__ == "__main__":
    main()
