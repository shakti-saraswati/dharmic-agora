"""
SAB moderation queue and decision logic.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .config import get_db_path
    from .models import ModerationStatus
    from .witness import WitnessChain
except ImportError:  # Allow running as script
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agora.config import get_db_path
    from agora.models import ModerationStatus
    from agora.witness import WitnessChain


class ModerationStore:
    """Moderation queue store backed by SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or get_db_path()
        self._init_db()
        self.witness = WitnessChain(self.db_path)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS moderation_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type TEXT NOT NULL CHECK(content_type IN ('post', 'comment')),
                    content_id INTEGER,
                    post_id INTEGER,
                    parent_id INTEGER,
                    content TEXT NOT NULL,
                    author_address TEXT NOT NULL,
                    gate_evidence_hash TEXT NOT NULL,
                    gate_results_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewer_address TEXT,
                    published_content_id INTEGER,
                    signature TEXT,
                    signed_at TEXT
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mod_queue_status ON moderation_queue(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mod_queue_author ON moderation_queue(author_address)")

    def enqueue(
        self,
        content_type: str,
        content: str,
        author_address: str,
        gate_evidence_hash: str,
        gate_results: List[Dict[str, Any]],
        created_at: Optional[str] = None,
        post_id: Optional[int] = None,
        parent_id: Optional[int] = None,
        signature: Optional[str] = None,
        signed_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO moderation_queue (
                    content_type, content, author_address, gate_evidence_hash,
                    gate_results_json, status, reason, created_at, post_id,
                    parent_id, signature, signed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_type,
                    content,
                    author_address,
                    gate_evidence_hash,
                    json.dumps(gate_results),
                    ModerationStatus.PENDING.value,
                    None,
                    created_at,
                    post_id,
                    parent_id,
                    signature,
                    signed_at,
                ),
            )
            queue_id = cursor.lastrowid
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            row = cursor.fetchone()
        return dict(row)

    def list_queue(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    """
                    SELECT * FROM moderation_queue
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (status, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM moderation_queue
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_item(self, queue_id: int) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def approve(self, queue_id: int, reviewer_address: str, reason: Optional[str] = None) -> Dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            item = cursor.fetchone()
            if not item:
                raise ValueError("Queue item not found")
            item = dict(item)
            if item["status"] == ModerationStatus.APPROVED.value:
                return item

            created_at = item["created_at"]
            published_id = item.get("published_content_id")
            if not published_id:
                if item["content_type"] == "post":
                    cursor.execute(
                        """
                        INSERT INTO posts (content, author_address, gate_evidence_hash, created_at, signature, signed_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item["content"],
                            item["author_address"],
                            item["gate_evidence_hash"],
                            created_at,
                            item.get("signature"),
                            item.get("signed_at"),
                        ),
                    )
                    published_id = cursor.lastrowid
                else:
                    cursor.execute(
                        """
                        INSERT INTO comments (post_id, content, author_address, gate_evidence_hash, parent_id, created_at, signature, signed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item["post_id"],
                            item["content"],
                            item["author_address"],
                            item["gate_evidence_hash"],
                            item["parent_id"],
                            created_at,
                            item.get("signature"),
                            item.get("signed_at"),
                        ),
                    )
                    published_id = cursor.lastrowid
                    # Update post comment count
                    cursor.execute(
                        "UPDATE posts SET comment_count = comment_count + 1 WHERE id = ?",
                        (item["post_id"],),
                    )

                gate_results = json.loads(item["gate_results_json"])
                for result in gate_results:
                    cursor.execute(
                        """
                        INSERT INTO gates_log (content_type, content_id, gate_name, passed,
                                               score, evidence, run_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item["content_type"],
                            published_id,
                            result["name"],
                            int(result["passed"]),
                            result.get("score", 0.0),
                            json.dumps(result.get("evidence", {})),
                            created_at,
                        ),
                    )

            cursor.execute(
                """
                UPDATE moderation_queue
                SET status = ?, reason = ?, reviewed_at = ?, reviewer_address = ?, published_content_id = ?, content_id = ?
                WHERE id = ?
                """,
                (
                    ModerationStatus.APPROVED.value,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                    reviewer_address,
                    published_id,
                    published_id,
                    queue_id,
                ),
            )
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            updated = dict(cursor.fetchone())

        self.witness.record(
            "moderation_approved",
            reviewer_address,
            {
                "queue_id": queue_id,
                "content_type": updated["content_type"],
                "published_content_id": updated["published_content_id"],
                "reason": reason,
            },
            content_id=str(queue_id),
        )
        return updated

    def reject(self, queue_id: int, reviewer_address: str, reason: Optional[str] = None) -> Dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            item = cursor.fetchone()
            if not item:
                raise ValueError("Queue item not found")
            item = dict(item)
            if item["status"] == ModerationStatus.REJECTED.value:
                return item

            cursor.execute(
                """
                UPDATE moderation_queue
                SET status = ?, reason = ?, reviewed_at = ?, reviewer_address = ?
                WHERE id = ?
                """,
                (
                    ModerationStatus.REJECTED.value,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                    reviewer_address,
                    queue_id,
                ),
            )
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            updated = dict(cursor.fetchone())

        self.witness.record(
            "moderation_rejected",
            reviewer_address,
            {
                "queue_id": queue_id,
                "content_type": updated["content_type"],
                "reason": reason,
            },
            content_id=str(queue_id),
        )
        return updated

    def appeal(self, queue_id: int, requester_address: str, reason: Optional[str] = None) -> Dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            item = cursor.fetchone()
            if not item:
                raise ValueError("Queue item not found")
            item = dict(item)
            if item["status"] == ModerationStatus.APPEALED.value:
                return item

            cursor.execute(
                """
                UPDATE moderation_queue
                SET status = ?, reason = ?, reviewed_at = ?, reviewer_address = ?
                WHERE id = ?
                """,
                (
                    ModerationStatus.APPEALED.value,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                    requester_address,
                    queue_id,
                ),
            )
            cursor.execute("SELECT * FROM moderation_queue WHERE id = ?", (queue_id,))
            updated = dict(cursor.fetchone())

        self.witness.record(
            "moderation_appealed",
            requester_address,
            {
                "queue_id": queue_id,
                "content_type": updated["content_type"],
                "reason": reason,
            },
            content_id=str(queue_id),
        )
        return updated
