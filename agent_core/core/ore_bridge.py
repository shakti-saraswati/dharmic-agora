#!/usr/bin/env python3
"""ORE bridge: turn any input file into an auditable Markdown artifact.

This is the "semantic kernel" for the hyperbolic chamber:
  - compute provenance (sha256, size)
  - write a frontmatter-rich artifact
  - append a WitnessEvent (hash-chained)

No external APIs required; pluggable later.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from core.frontmatter_v2 import render_frontmatter, validate_frontmatter_v2
from core.witness_event import append_event, new_event, verify_log


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _default_timestamp_with_tz() -> str:
    # Keep "WITA" because it's a strong convention in your current ops.
    # If you want auto-detection, wire it via env var later.
    return datetime.now().strftime("%H:%M:%S") + " WITA"


def build_ore_artifact(
    *,
    input_path: Path,
    out_path: Path,
    title: str,
    agent: str,
    system_model: str,
    agent_id: str,
    location: str,
    factory_stage: str,
    yosemite_grade: str,
    readiness_measure: str,
    connecting_files: List[str],
    agent_tags: List[str],
    pinned: bool,
    required_reading: bool,
    jikoku: str,
) -> str:
    sha256 = _sha256_file(input_path)
    size = input_path.stat().st_size

    fm: Dict[str, Any] = {
        "title": title,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": _default_timestamp_with_tz(),
        "location": location,
        "agent": agent,
        "system_model": system_model,
        "agent_id": agent_id,
        "jikoku": jikoku,
        "connecting_files": connecting_files,
        "agent_tags": agent_tags,
        "factory_stage": factory_stage,
        "yosemite_grade": yosemite_grade,
        "readiness_measure": readiness_measure,
        "required_reading": required_reading,
        "pinned": pinned,
        "ore_input_path": str(input_path),
        "ore_input_sha256": sha256,
        "ore_input_bytes": size,
    }

    errors = validate_frontmatter_v2(fm)
    if errors:
        raise ValueError("Frontmatter validation failed: " + "; ".join(errors))

    head = ""
    try:
        head = input_path.read_text(encoding="utf-8", errors="replace")[:2000]
    except Exception:
        head = "[binary input]"

    body = f"""# ORE Artifact

## Provenance
- input: `{input_path}`
- sha256: `{sha256}`
- bytes: `{size}`

## Preview (first 2000 chars)
```text
{head}
```

## Notes
- This file is a provenance wrapper. Downstream agents should operate on the input and
  emit new artifacts rather than editing this one.
"""

    return render_frontmatter(fm) + "\n" + body


def ingest(
    *,
    input_path: Path,
    out_path: Path,
    witness_log: Path,
    agent: str,
    system_model: str,
    agent_id: str,
    location: str,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    title = f"ORE: {input_path.name}"
    jikoku = f"Time-Place Nexus - {datetime.now().strftime('%Y-%m-%d %H:%M')} WITA, {location}; ORE ingestion"
    md = build_ore_artifact(
        input_path=input_path,
        out_path=out_path,
        title=title,
        agent=agent,
        system_model=system_model,
        agent_id=agent_id,
        location=location,
        factory_stage="Staging",
        yosemite_grade="5.10b",
        readiness_measure="70",
        connecting_files=["README.md", "MANIFEST.md", "NVIDIA_POWER_REPO_IRON_ORE.md"],
        agent_tags=["@VAJRA", "@MMK"],
        pinned=False,
        required_reading=False,
        jikoku=jikoku,
    )
    out_path.write_text(md, encoding="utf-8")

    ev = new_event(
        actor=agent,
        action="ore_ingest",
        subject=str(out_path),
        meta={
            "input_path": str(input_path),
            "output_path": str(out_path),
            "system_model": system_model,
            "agent_id": agent_id,
        },
    )
    append_event(witness_log, ev)
    return out_path


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ORE bridge (provenance wrapper)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="Ingest a file and emit an ORE Markdown artifact")
    ing.add_argument("input", help="Path to input file")
    ing.add_argument("--out", default="artifacts/ore", help="Output directory (default: artifacts/ore)")
    ing.add_argument("--witness-log", default="witness_events/WITNESS_EVENTS.jsonl", help="Witness JSONL log path")
    ing.add_argument("--agent", default=os.getenv("AIKAGRYA_AGENT", "RUSHABDEV"))
    ing.add_argument("--system-model", default=os.getenv("AIKAGRYA_MODEL", "CODEX"))
    ing.add_argument("--agent-id", default=os.getenv("AIKAGRYA_AGENT_ID", "001"))
    ing.add_argument("--location", default=os.getenv("AIKAGRYA_LOCATION", "Denpasar, Bali, ID"))

    ver = sub.add_parser("verify", help="Verify witness log integrity")
    ver.add_argument("--witness-log", default="witness_events/WITNESS_EVENTS.jsonl", help="Witness JSONL log path")

    args = p.parse_args(argv)

    if args.cmd == "ingest":
        input_path = Path(args.input).expanduser().resolve()
        out_dir = Path(args.out)
        out_path = out_dir / f"{input_path.stem}_ORE.md"
        witness_log = Path(args.witness_log)
        ingest(
            input_path=input_path,
            out_path=out_path,
            witness_log=witness_log,
            agent=args.agent,
            system_model=args.system_model,
            agent_id=args.agent_id,
            location=args.location,
        )
        print(str(out_path))
        return 0

    if args.cmd == "verify":
        res = verify_log(Path(args.witness_log))
        if not res["valid"]:
            for e in res["errors"]:
                print(e)
            return 1
        print(f"OK ({res['records']} records)")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

