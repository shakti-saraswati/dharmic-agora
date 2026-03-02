from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def _canonical_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _insert_witness(
    conn: sqlite3.Connection,
    *,
    row_id: int,
    spark_id: Optional[int],
    witness_id: str,
    action: str,
    payload_obj: Dict[str, Any],
    timestamp: str,
    prev_hash: str,
) -> str:
    payload_json = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    material = {
        "spark_id": spark_id,
        "witness_id": witness_id,
        "signature": "deadbeef",
        "action": action,
        "payload": payload_json,
        "timestamp": timestamp,
        "prev_hash": prev_hash,
    }
    entry_hash = _sha256_hex(_canonical_bytes(material))
    conn.execute(
        """
        INSERT INTO witness_chain (id, spark_id, witness_id, signature, action, payload, timestamp, prev_hash, hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (row_id, spark_id, witness_id, "deadbeef", action, payload_json, timestamp, prev_hash, entry_hash),
    )
    return entry_hash


def _make_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE witness_chain (
                id INTEGER PRIMARY KEY,
                spark_id INTEGER,
                witness_id TEXT NOT NULL,
                signature TEXT NOT NULL,
                action TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                prev_hash TEXT,
                hash TEXT NOT NULL
            )
            """
        )
        h1 = _insert_witness(
            conn,
            row_id=1,
            spark_id=101,
            witness_id="agent-a",
            action="submit",
            payload_obj={"content_sha256": "abc"},
            timestamp="2026-03-03T00:00:00+00:00",
            prev_hash="genesis",
        )
        _insert_witness(
            conn,
            row_id=2,
            spark_id=101,
            witness_id="agent-b",
            action="affirm",
            payload_obj={"note": "looks good"},
            timestamp="2026-03-03T00:01:00+00:00",
            prev_hash=h1,
        )
        conn.commit()
    finally:
        conn.close()


def test_verify_witness_chain_valid(tmp_path: Path):
    db_path = tmp_path / "valid.db"
    _make_db(db_path)

    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_witness_chain.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--db", str(db_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = json.loads(proc.stdout)
    assert body["ok"] is True
    assert body["entries_checked"] == 2


def test_verify_witness_chain_tamper_detected(tmp_path: Path):
    db_path = tmp_path / "tampered.db"
    _make_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE witness_chain SET hash = ? WHERE id = 2", ("badbadbad",))
        conn.commit()
    finally:
        conn.close()

    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_witness_chain.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--db", str(db_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    body = json.loads(proc.stdout)
    assert body["ok"] is False
    assert body["error"] == "chain_invalid"
    assert len(body["invalid_entries"]) >= 1
