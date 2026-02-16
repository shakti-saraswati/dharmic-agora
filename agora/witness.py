"""
SAB Witness Chain

Hash-chained audit log for tamper-evident moderation decisions and system actions.

WITNESS LAYER BOUNDARY:
- This module is the SABP witness (publication provenance): queue decisions,
  moderation transitions, and runtime/admin actions in the API layer.
- Artifact derivation provenance is intentionally separate and lives in
  `agent_core/core/witness_event.py`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .config import get_db_path
except ImportError:  # Allow running as script
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agora.config import get_db_path


class WitnessChain:
    """Hash-chained audit log. Every entry references the previous hash."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS witness_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                agent_address TEXT,
                content_id TEXT,
                details TEXT NOT NULL,
                prev_hash TEXT,
                hash TEXT NOT NULL
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_witness_content ON witness_chain(content_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_witness_action ON witness_chain(action)")
        conn.commit()
        conn.close()

    def _get_last_hash(self, cursor: sqlite3.Cursor) -> Optional[str]:
        cursor.execute("SELECT hash FROM witness_chain ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else None

    def record(self, action: str, agent_id: str, details: Dict[str, Any], content_id: Optional[str] = None) -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "agent_id": agent_id,
            "details": details,
            "prev_hash": None,
            "content_id": content_id,
        }

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        prev_hash = self._get_last_hash(cursor)
        entry["prev_hash"] = prev_hash

        entry_bytes = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
        entry_hash = hashlib.sha256(entry_bytes).hexdigest()
        entry["hash"] = entry_hash

        cursor.execute(
            """
            INSERT INTO witness_chain (timestamp, action, agent_address, content_id, details, prev_hash, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["timestamp"],
                entry["action"],
                entry["agent_id"],
                entry["content_id"],
                json.dumps(details),
                entry["prev_hash"],
                entry["hash"],
            ),
        )
        conn.commit()
        conn.close()
        return entry

    def list_entries(
        self,
        content_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if content_id is not None:
            cursor.execute(
                """
                SELECT * FROM witness_chain
                WHERE content_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (str(content_id), limit, offset),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM witness_chain
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def verify_chain(self, entries: List[Dict[str, Any]]) -> bool:
        """Verify no entries have been tampered with."""
        prev_hash = None
        for entry in entries:
            if entry.get("prev_hash") != prev_hash:
                return False
            check = {k: v for k, v in entry.items() if k != "hash"}
            expected = hashlib.sha256(
                json.dumps(check, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if entry.get("hash") != expected:
                return False
            prev_hash = entry.get("hash")
        return True
