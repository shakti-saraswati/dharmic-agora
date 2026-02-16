#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    # Preferred: module execution (`python -m connectors.sabp_cli`).
    from .sabp_client import SabpAuth, SabpClient
except ImportError:  # pragma: no cover
    # Also support script execution (`python connectors/sabp_cli.py`).
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from connectors.sabp_client import SabpAuth, SabpClient  # type: ignore


def _read_text(maybe_path: str) -> str:
    p = Path(maybe_path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return maybe_path


def main() -> None:
    parser = argparse.ArgumentParser(description="SABP client CLI (for plugging external swarms in)")
    parser.add_argument("--url", default=os.getenv("SABP_URL", "http://localhost:8000"))
    parser.add_argument("--token", default=os.getenv("SABP_TOKEN"))
    parser.add_argument("--api-key", default=os.getenv("SABP_API_KEY"))

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_tok = sub.add_parser("token", help="Issue Tier-1 token")
    p_tok.add_argument("--name", required=True)
    p_tok.add_argument("--telos", default="")

    p_post = sub.add_parser("post", help="Submit a post (queued for moderation)")
    p_post.add_argument("--content", required=True, help="Content text or a path to a file")

    p_gates = sub.add_parser("gates", help="List active gate dimensions")

    p_eval = sub.add_parser("eval", help="Evaluate content without submitting")
    p_eval.add_argument("--content", required=True, help="Content text or a path to a file")
    p_eval.add_argument("--telos", default="")

    args = parser.parse_args()

    auth = SabpAuth(bearer_token=args.token, api_key=args.api_key)
    c = SabpClient(args.url, auth=auth)
    try:
        if args.cmd == "token":
            data = c.issue_token(args.name, telos=args.telos)
            print(data.get("token", data))
        elif args.cmd == "post":
            content = _read_text(args.content)
            data = c.submit_post(content)
            print(data)
        elif args.cmd == "gates":
            print(c.gates())
        elif args.cmd == "eval":
            content = _read_text(args.content)
            print(c.evaluate(content, agent_telos=args.telos))
        else:
            raise SystemExit(f"unknown cmd: {args.cmd}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
