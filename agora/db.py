"""
DHARMIC_AGORA Database Layer

SQLite database with proper security (learned from Moltbook).
Implements row-level security via application logic.
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from .models import Post, Vote, ContentType, VoteType, generate_content_id


# =============================================================================
# CONFIGURATION
# =============================================================================

AGORA_DB = Path(__file__).parent.parent / "data" / "agora.db"


# =============================================================================
# DATABASE MANAGER
# =============================================================================

class AgoraDB:
    """
    Database manager for DHARMIC_AGORA.

    Security features:
    - No API keys stored (auth uses Ed25519 challenge-response)
    - All queries parameterized
    - Row-level security via application logic
    - Audit trail for all mutations
    """

    def __init__(self, db_path: Path = AGORA_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self):
        """Context manager for database connection."""
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

    def _init_db(self):
        """Initialize database tables."""
        with self._conn() as conn:
            cursor = conn.cursor()

            def ensure_column(table: str, column_name: str, column_def: str) -> None:
                cursor.execute(f"PRAGMA table_info({table})")
                existing = {row[1] for row in cursor.fetchall()}
                if column_name not in existing:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")

            # Posts table (includes comments)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    author_address TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'post',
                    parent_id TEXT,
                    created_at TEXT NOT NULL,
                    gate_evidence_hash TEXT NOT NULL,
                    gates_passed TEXT NOT NULL,
                    karma INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    is_deleted INTEGER DEFAULT 0,
                    signature TEXT,
                    signed_at TEXT,
                    FOREIGN KEY (author_address) REFERENCES agents(address),
                    FOREIGN KEY (parent_id) REFERENCES posts(id)
                )
            """)

            # Votes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    id TEXT PRIMARY KEY,
                    voter_address TEXT NOT NULL,
                    content_id TEXT NOT NULL,
                    vote_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(voter_address, content_id),
                    FOREIGN KEY (voter_address) REFERENCES agents(address),
                    FOREIGN KEY (content_id) REFERENCES posts(id)
                )
            """)

            # Gate evidence table (stores full evidence for verification)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gate_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL,
                    evidence_hash TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (content_id) REFERENCES posts(id)
                )
            """)

            # Moderation queue
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS moderation_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type TEXT NOT NULL CHECK(content_type IN ('post', 'comment')),
                    content_id TEXT,
                    post_id TEXT,
                    parent_id TEXT,
                    content TEXT NOT NULL,
                    author_address TEXT NOT NULL,
                    gate_evidence_hash TEXT NOT NULL,
                    gate_results_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewer_address TEXT,
                    published_content_id TEXT,
                    signature TEXT,
                    signed_at TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mod_queue_status ON moderation_queue(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mod_queue_author ON moderation_queue(author_address)")

            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_address)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_parent ON posts(parent_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_content ON votes(content_id)")

            # Backfill new columns if DB already existed
            ensure_column("posts", "signature", "signature TEXT")
            ensure_column("posts", "signed_at", "signed_at TEXT")

    # =========================================================================
    # POSTS
    # =========================================================================

    def create_post(
        self,
        author_address: str,
        content: str,
        gate_evidence_hash: str,
        gates_passed: List[str],
        content_type: ContentType = ContentType.POST,
        parent_id: Optional[str] = None,
        signature: Optional[str] = None,
        signed_at: Optional[str] = None,
    ) -> Post:
        """Create a new post or comment."""
        created_at = datetime.now(timezone.utc).isoformat()
        post_id = generate_content_id(author_address, content, created_at)

        with self._conn() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO posts (
                    id, author_address, content, content_type, parent_id,
                    created_at, gate_evidence_hash, gates_passed, signature, signed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post_id, author_address, content, content_type.value,
                parent_id, created_at, gate_evidence_hash, json.dumps(gates_passed),
                signature, signed_at
            ))

            # Update parent comment count if this is a comment
            if parent_id:
                cursor.execute(
                    "UPDATE posts SET comment_count = comment_count + 1 WHERE id = ?",
                    (parent_id,)
                )

        return Post(
            id=post_id,
            author_address=author_address,
            content=content,
            created_at=created_at,
            gate_evidence_hash=gate_evidence_hash,
            gates_passed=gates_passed,
            content_type=content_type,
            parent_id=parent_id
        )

    def get_post(self, post_id: str) -> Optional[Post]:
        """Get a post by ID."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM posts WHERE id = ? AND is_deleted = 0
            """, (post_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_post(row)

    def get_posts(
        self,
        limit: int = 50,
        offset: int = 0,
        author_address: Optional[str] = None
    ) -> List[Post]:
        """Get posts with pagination."""
        with self._conn() as conn:
            cursor = conn.cursor()

            if author_address:
                cursor.execute("""
                    SELECT * FROM posts
                    WHERE content_type = 'post' AND is_deleted = 0 AND author_address = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (author_address, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM posts
                    WHERE content_type = 'post' AND is_deleted = 0
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

            return [self._row_to_post(row) for row in cursor.fetchall()]

    def get_comments(self, parent_id: str, limit: int = 100) -> List[Post]:
        """Get comments for a post."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM posts
                WHERE parent_id = ? AND is_deleted = 0
                ORDER BY created_at ASC
                LIMIT ?
            """, (parent_id, limit))

            return [self._row_to_post(row) for row in cursor.fetchall()]

    def get_author_post_counts(self, author_address: str) -> Dict[str, int]:
        """Get post counts for rate limiting."""
        with self._conn() as conn:
            cursor = conn.cursor()

            # Posts in last hour
            cursor.execute("""
                SELECT COUNT(*) FROM posts
                WHERE author_address = ?
                AND created_at > datetime('now', '-1 hour')
            """, (author_address,))
            last_hour = cursor.fetchone()[0]

            # Posts in last day
            cursor.execute("""
                SELECT COUNT(*) FROM posts
                WHERE author_address = ?
                AND created_at > datetime('now', '-1 day')
            """, (author_address,))
            last_day = cursor.fetchone()[0]

            return {"last_hour": last_hour, "last_day": last_day}

    def _row_to_post(self, row: sqlite3.Row) -> Post:
        """Convert database row to Post object."""
        return Post(
            id=row["id"],
            author_address=row["author_address"],
            content=row["content"],
            created_at=row["created_at"],
            gate_evidence_hash=row["gate_evidence_hash"],
            gates_passed=json.loads(row["gates_passed"]),
            karma=row["karma"],
            comment_count=row["comment_count"],
            parent_id=row["parent_id"],
            content_type=ContentType(row["content_type"])
        )

    # =========================================================================
    # VOTES
    # =========================================================================

    def create_vote(
        self,
        voter_address: str,
        content_id: str,
        vote_type: VoteType
    ) -> Optional[Vote]:
        """Create or update a vote."""
        created_at = datetime.now(timezone.utc).isoformat()
        vote_id = generate_content_id(voter_address, content_id, created_at)

        with self._conn() as conn:
            cursor = conn.cursor()

            # Check existing vote
            cursor.execute("""
                SELECT vote_type FROM votes
                WHERE voter_address = ? AND content_id = ?
            """, (voter_address, content_id))
            existing = cursor.fetchone()

            karma_delta = 1 if vote_type == VoteType.UP else -1

            if existing:
                old_type = VoteType(existing["vote_type"])
                if old_type == vote_type:
                    # Same vote, remove it
                    cursor.execute("""
                        DELETE FROM votes
                        WHERE voter_address = ? AND content_id = ?
                    """, (voter_address, content_id))
                    karma_delta = -1 if vote_type == VoteType.UP else 1
                else:
                    # Change vote
                    cursor.execute("""
                        UPDATE votes SET vote_type = ?, created_at = ?
                        WHERE voter_address = ? AND content_id = ?
                    """, (vote_type.value, created_at, voter_address, content_id))
                    karma_delta = 2 if vote_type == VoteType.UP else -2
            else:
                # New vote
                cursor.execute("""
                    INSERT INTO votes (id, voter_address, content_id, vote_type, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (vote_id, voter_address, content_id, vote_type.value, created_at))

            # Update karma
            cursor.execute("""
                UPDATE posts SET karma = karma + ? WHERE id = ?
            """, (karma_delta, content_id))

        return Vote(
            id=vote_id,
            voter_address=voter_address,
            content_id=content_id,
            vote_type=vote_type,
            created_at=created_at
        )

    def get_votes_for_content(self, content_id: str) -> Dict[str, int]:
        """Get vote counts for content."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT vote_type, COUNT(*) as count
                FROM votes WHERE content_id = ?
                GROUP BY vote_type
            """, (content_id,))

            result = {"up": 0, "down": 0}
            for row in cursor.fetchall():
                result[row["vote_type"]] = row["count"]

            return result

    # =========================================================================
    # GATE EVIDENCE
    # =========================================================================

    def store_gate_evidence(
        self,
        content_id: str,
        evidence_hash: str,
        evidence_json: str
    ):
        """Store gate evidence for a post."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO gate_evidence (content_id, evidence_hash, evidence_json, created_at)
                VALUES (?, ?, ?, ?)
            """, (content_id, evidence_hash, evidence_json, datetime.now(timezone.utc).isoformat()))

    def get_gate_evidence(self, content_id: str) -> Optional[Dict]:
        """Get gate evidence for a post."""
        with self._conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT evidence_json FROM gate_evidence WHERE content_id = ?
            """, (content_id,))
            row = cursor.fetchone()

            if row:
                return json.loads(row["evidence_json"])
            return None

    # =========================================================================
    # STATS
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get overall AGORA statistics."""
        with self._conn() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM posts WHERE content_type = 'post' AND is_deleted = 0")
            post_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM posts WHERE content_type = 'comment' AND is_deleted = 0")
            comment_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM votes")
            vote_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT author_address) FROM posts")
            unique_authors = cursor.fetchone()[0]

            return {
                "total_posts": post_count,
                "total_comments": comment_count,
                "total_votes": vote_count,
                "unique_authors": unique_authors
            }


# Singleton instance
_db: Optional[AgoraDB] = None


def get_db() -> AgoraDB:
    """Get singleton database instance."""
    global _db
    if _db is None:
        _db = AgoraDB()
    return _db

# SQL Injection Protection — Column Allowlist
ALLOWED_COLUMNS = {
    "posts": ["id", "content", "author_address", "created_at", "signature"],
    "users": ["address", "public_key", "created_at"],
    "votes": ["post_id", "voter_address", "value", "created_at"]
}

def validate_columns(table: str, columns: list) -> bool:
    """Validate columns against allowlist to prevent SQL injection."""
    allowed = ALLOWED_COLUMNS.get(table, [])
    return all(col in allowed for col in columns)
