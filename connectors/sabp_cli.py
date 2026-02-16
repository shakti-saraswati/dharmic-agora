#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

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


def _read_json(maybe_path_or_json: str) -> dict[str, Any]:
    raw = _read_text(maybe_path_or_json)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def _read_json_events(maybe_path_or_json: str) -> list[dict[str, Any]]:
    raw = _read_text(maybe_path_or_json).strip()
    if not raw:
        return []
    if raw.startswith("["):
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("expected JSON array of payload objects")
        out: list[dict[str, Any]] = []
        for idx, item in enumerate(parsed):
            if not isinstance(item, dict):
                raise ValueError(f"expected JSON object at index {idx}")
            out.append(item)
        return out

    out: list[dict[str, Any]] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        item = json.loads(text)
        if not isinstance(item, dict):
            raise ValueError(f"expected JSON object at line {lineno}")
        out.append(item)
    return out


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

    p_identity = sub.add_parser("identity", help="Register agent identity packet")
    p_identity.add_argument("--packet", required=True, help="JSON packet or path to JSON file")

    p_dgc = sub.add_parser("ingest-dgc", help="Ingest one DGC signal payload")
    p_dgc.add_argument("--payload", required=True, help="JSON payload or path to JSON file")
    p_dgc.add_argument("--dgc-secret", default=os.getenv("SAB_DGC_SHARED_SECRET"))

    p_dgc_batch = sub.add_parser("ingest-dgc-batch", help="Ingest multiple DGC payloads (JSON array or JSONL)")
    p_dgc_batch.add_argument("--payloads", required=True, help="JSON array/JSONL text or path")
    p_dgc_batch.add_argument("--dgc-secret", default=os.getenv("SAB_DGC_SHARED_SECRET"))
    p_dgc_batch.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue ingesting remaining payloads when one fails",
    )

    p_trust = sub.add_parser("trust", help="Query trust gradient history for an agent")
    p_trust.add_argument("--address", required=True)
    p_trust.add_argument("--limit", type=int, default=50)

    p_landscape = sub.add_parser("landscape", help="Query convergence landscape view")
    p_landscape.add_argument("--limit", type=int, default=200)

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
        elif args.cmd == "identity":
            packet = _read_json(args.packet)
            print(c.register_identity(packet))
        elif args.cmd == "ingest-dgc":
            if not args.dgc_secret:
                raise SystemExit("missing --dgc-secret or SAB_DGC_SHARED_SECRET")
            payload = _read_json(args.payload)
            print(c.ingest_dgc_signal(payload, dgc_shared_secret=args.dgc_secret))
        elif args.cmd == "ingest-dgc-batch":
            if not args.dgc_secret:
                raise SystemExit("missing --dgc-secret or SAB_DGC_SHARED_SECRET")
            payloads = _read_json_events(args.payloads)
            if not payloads:
                raise SystemExit("no payloads found")
            ok = 0
            failed = 0
            for idx, payload in enumerate(payloads, start=1):
                try:
                    result = c.ingest_dgc_signal(payload, dgc_shared_secret=args.dgc_secret)
                    ok += 1
                    print(json.dumps({"index": idx, "status": "ok", "event_id": result.get("event_id")}))
                except Exception as exc:  # pragma: no cover - network error path
                    failed += 1
                    print(json.dumps({"index": idx, "status": "error", "error": str(exc)}))
                    if not args.continue_on_error:
                        raise
            print(json.dumps({"summary": {"ok": ok, "failed": failed, "total": len(payloads)}}))
            if failed:
                raise SystemExit(1)
        elif args.cmd == "trust":
            print(c.trust_history(args.address, limit=args.limit))
        elif args.cmd == "landscape":
            print(c.convergence_landscape(limit=args.limit))
        else:
            raise SystemExit(f"unknown cmd: {args.cmd}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
