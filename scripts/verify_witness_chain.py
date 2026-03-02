#!/usr/bin/env python3
"""Verify witness chain integrity for SAB spark database."""

from __future__ import annotations

import argparse
import json
import hashlib
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _canonical_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_chain(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists():
        return {
            "ok": False,
            "db_path": str(db_path),
            "error": "db_not_found",
            "entries_checked": 0,
            "invalid_entries": [],
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        table_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='witness_chain'"
        ).fetchone()
        if table_row is None:
            return {
                "ok": False,
                "db_path": str(db_path),
                "error": "missing_witness_chain_table",
                "entries_checked": 0,
                "invalid_entries": [],
            }

        rows = conn.execute(
            """
            SELECT id, spark_id, witness_id, signature, action, payload, timestamp, prev_hash, hash
            FROM witness_chain
            ORDER BY id ASC
            """
        ).fetchall()

        invalid_entries: List[Dict[str, Any]] = []
        prev_hash_by_stream: Dict[Optional[int], str] = {}

        for row in rows:
            stream_key: Optional[int] = row["spark_id"]
            expected_prev = prev_hash_by_stream.get(stream_key, "genesis")
            if str(row["prev_hash"]) != expected_prev:
                invalid_entries.append(
                    {
                        "id": int(row["id"]),
                        "reason": "prev_hash_mismatch",
                        "expected": expected_prev,
                        "actual": str(row["prev_hash"]),
                        "spark_id": stream_key,
                    }
                )

            material = {
                "spark_id": row["spark_id"],
                "witness_id": row["witness_id"],
                "signature": row["signature"],
                "action": row["action"],
                "payload": row["payload"],
                "timestamp": row["timestamp"],
                "prev_hash": row["prev_hash"],
            }
            expected_hash = _sha256_hex(_canonical_bytes(material))
            if str(row["hash"]) != expected_hash:
                invalid_entries.append(
                    {
                        "id": int(row["id"]),
                        "reason": "hash_mismatch",
                        "expected": expected_hash,
                        "actual": str(row["hash"]),
                        "spark_id": stream_key,
                    }
                )

            prev_hash_by_stream[stream_key] = str(row["hash"])

        return {
            "ok": len(invalid_entries) == 0,
            "db_path": str(db_path),
            "error": "" if len(invalid_entries) == 0 else "chain_invalid",
            "entries_checked": len(rows),
            "invalid_entries": invalid_entries,
            "streams_checked": len(prev_hash_by_stream),
        }
    finally:
        conn.close()


def _main() -> int:
    parser = argparse.ArgumentParser(description="Verify SAB witness chain integrity.")
    parser.add_argument("--db", dest="db", default="data/sab.db", help="Path to SQLite DB")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    result = verify_chain(Path(args.db))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["ok"]:
            print(f"OK: witness chain valid ({result['entries_checked']} entries)")
        else:
            print(f"FAIL: witness chain invalid ({len(result['invalid_entries'])} issues)")
            for issue in result["invalid_entries"][:20]:
                print(
                    f"- id={issue.get('id')} spark={issue.get('spark_id')} "
                    f"reason={issue.get('reason')} expected={issue.get('expected')} actual={issue.get('actual')}"
                )

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(_main())
