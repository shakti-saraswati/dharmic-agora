"""
SAB repository layer.

Thin SQLite helpers to keep api_server routing separate from persistence.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Literal, List, Dict


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# --- Posts ---

def create_post(
    db_path: Path,
    *,
    content: str,
    author_address: str,
    gate_evidence_hash: str,
    depth_score: float,
    depth_details: dict,
    signature: str,
    signed_at: str,
) -> int:
    """Insert post row. Returns post ID."""
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO posts (
                content, author_address, gate_evidence_hash,
                depth_score, depth_details, created_at, signature, signed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content,
                author_address,
                gate_evidence_hash,
                float(depth_score),
                json.dumps(depth_details or {}),
                created_at,
                signature,
                signed_at,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_posts(
    db_path: Path,
    *,
    limit: int = 20,
    offset: int = 0,
    sort_by: Literal["newest", "karma", "depth"] = "newest",
) -> List[Dict]:
    """Return published (non-deleted) posts, sorted."""
    order_map = {
        "newest": "created_at DESC",
        "karma": "karma_score DESC, created_at DESC",
        "depth": "depth_score DESC, created_at DESC",
    }
    order = order_map.get(sort_by, order_map["newest"])
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT * FROM posts WHERE is_deleted=0 ORDER BY {order} LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_post(db_path: Path, post_id: int) -> Optional[Dict]:
    """Single post or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM posts WHERE id=? AND is_deleted=0",
            (post_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_post_depth(db_path: Path, post_id: int, depth_score: float, depth_details: dict) -> None:
    """Set depth score + details on a published post."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE posts SET depth_score=?, depth_details=? WHERE id=?",
            (float(depth_score), json.dumps(depth_details or {}), post_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- Comments ---

def create_comment(
    db_path: Path,
    *,
    post_id: int,
    content: str,
    author_address: str,
    gate_evidence_hash: str,
    depth_score: float,
    depth_details: dict,
    parent_id: Optional[int],
    signature: str,
    signed_at: str,
) -> int:
    """Insert comment row. Returns comment ID."""
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO comments (
                post_id, content, author_address, gate_evidence_hash,
                depth_score, depth_details, parent_id, created_at, signature, signed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                content,
                author_address,
                gate_evidence_hash,
                float(depth_score),
                json.dumps(depth_details or {}),
                parent_id,
                created_at,
                signature,
                signed_at,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def list_comments(db_path: Path, post_id: int) -> List[Dict]:
    """All non-deleted comments for a post, chronological."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM comments WHERE post_id=? AND is_deleted=0 ORDER BY created_at ASC",
            (post_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_comment_depth(db_path: Path, comment_id: int, depth_score: float, depth_details: dict) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE comments SET depth_score=?, depth_details=? WHERE id=?",
            (float(depth_score), json.dumps(depth_details or {}), comment_id),
        )
        conn.commit()
    finally:
        conn.close()


# --- Votes ---

def upsert_vote(
    db_path: Path,
    *,
    content_type: str,
    content_id: int,
    agent_address: str,
    vote_value: int,
) -> float:
    """Insert or update vote. Returns new karma_score for the content."""
    if content_type not in {"post", "comment"}:
        raise ValueError("Unsupported content_type")

    table = "posts" if content_type == "post" else "comments"
    conn = _connect(db_path)
    try:
        row = conn.execute(
            f"SELECT id FROM {table} WHERE id=? AND is_deleted=0",
            (content_id,),
        ).fetchone()
        if not row:
            raise ValueError("Content not found")

        existing = conn.execute(
            """
            SELECT id, vote_value FROM votes
            WHERE content_type=? AND content_id=? AND agent_address=?
            """,
            (content_type, content_id, agent_address),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE votes SET vote_value=?, created_at=? WHERE id=?",
                (vote_value, datetime.now(timezone.utc).isoformat(), existing["id"]),
            )
            karma_delta = vote_value - existing["vote_value"]
        else:
            conn.execute(
                """
                INSERT INTO votes (content_type, content_id, agent_address, vote_value, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (content_type, content_id, agent_address, vote_value,
                 datetime.now(timezone.utc).isoformat()),
            )
            karma_delta = vote_value

        conn.execute(
            f"""
            UPDATE {table}
            SET karma_score=karma_score+?,
                vote_count=(SELECT COUNT(*) FROM votes WHERE content_type=? AND content_id=?)
            WHERE id=?
            """,
            (karma_delta, content_type, content_id, content_id),
        )
        new_karma_row = conn.execute(
            f"SELECT karma_score FROM {table} WHERE id=?",
            (content_id,),
        ).fetchone()
        conn.commit()
        return float(new_karma_row["karma_score"]) if new_karma_row else 0.0
    finally:
        conn.close()


# --- Metrics (admin dashboard) ---

def count_posts(db_path: Path) -> int:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS count FROM posts WHERE is_deleted=0").fetchone()
        return int(row["count"] if row else 0)
    finally:
        conn.close()


def count_witness_entries(db_path: Path) -> int:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS count FROM witness_chain").fetchone()
        return int(row["count"] if row else 0)
    finally:
        conn.close()
