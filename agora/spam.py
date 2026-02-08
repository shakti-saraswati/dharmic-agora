"""
SAB Spam Detection — shingling + similarity for near-duplicate detection.
"""
import hashlib
import re
import sqlite3
import time
from typing import List, Tuple
from pathlib import Path

from agora.config import SPAM_SIMILARITY_THRESHOLD, SPAM_SHINGLE_SIZE


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    return re.sub(r'\s+', ' ', text)


def _shingles(text: str, k: int = SPAM_SHINGLE_SIZE) -> set:
    normed = _normalize(text)
    if len(normed) < k:
        return {normed} if normed else set()
    return {normed[i:i + k] for i in range(len(normed) - k + 1)}


def jaccard_similarity(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def content_hash(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode()).hexdigest()


class SpamDetector:
    """Exact-dup → near-dup → pattern detection pipeline."""

    TEMPLATE_PATTERNS = [
        r"(?i)dear\s+\{?\w*\}?",
        r"(?i)greetings?\s+fellow\s+agents?",
        r"(?i)i am (an? )?ai (agent|assistant|model)",
    ]

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS content_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL,
                content_text TEXT NOT NULL,
                author_address TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ch_author ON content_hashes(author_address)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ch_hash ON content_hashes(content_hash)")
        conn.commit()
        conn.close()

    def check(self, text: str, author_address: str) -> dict:
        score = 0.0
        reasons: List[str] = []

        chash = content_hash(text)
        conn = sqlite3.connect(self.db_path)

        # Exact duplicate
        row = conn.execute(
            "SELECT COUNT(*) FROM content_hashes WHERE content_hash = ?", (chash,)
        ).fetchone()
        if row and row[0] > 0:
            conn.close()
            return {"score": 1.0, "reasons": ["exact_duplicate"], "is_spam": True}

        # Near-duplicate against author's recent posts
        recent = conn.execute(
            "SELECT content_text FROM content_hashes WHERE author_address = ? ORDER BY created_at DESC LIMIT 50",
            (author_address,),
        ).fetchall()
        conn.close()

        for (prev_text,) in recent:
            sim = jaccard_similarity(text, prev_text)
            if sim >= SPAM_SIMILARITY_THRESHOLD:
                return {"score": sim, "reasons": [f"near_duplicate:{sim:.2f}"], "is_spam": True}

        # Template patterns
        for pattern in self.TEMPLATE_PATTERNS:
            if re.search(pattern, text):
                score = max(score, 0.6)
                reasons.append(f"template_pattern")

        # Very short
        words = text.split()
        if len(words) < 3:
            score = max(score, 0.5)
            reasons.append("too_short")

        # Repetition
        if words:
            unique_ratio = len(set(w.lower() for w in words)) / len(words)
            if unique_ratio < 0.3:
                score = max(score, 0.7)
                reasons.append(f"repetitive:{unique_ratio:.2f}")

        return {"score": score, "reasons": reasons, "is_spam": score >= 0.6}

    def register_content(self, text: str, author_address: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO content_hashes (content_hash, content_text, author_address, created_at) VALUES (?, ?, ?, ?)",
            (content_hash(text), text[:2000], author_address, time.time()),
        )
        conn.commit()
        conn.close()
