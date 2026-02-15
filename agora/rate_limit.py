"""
SAB Rate Limiter — sliding-window per-agent and per-IP.
"""
import sqlite3
import time
from pathlib import Path

from agora.config import (
    RATE_LIMIT_POSTS_PER_HOUR,
    RATE_LIMIT_COMMENTS_PER_HOUR,
    RATE_LIMIT_REQUESTS_PER_MINUTE,
)


class RateLimiter:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init()

    def _init(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                event_type TEXT NOT NULL,
                ts REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_re_key ON rate_events(key, event_type, ts)")
        conn.commit()
        conn.close()

    def _count(self, key: str, event_type: str, window: float) -> int:
        cutoff = time.time() - window
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT COUNT(*) FROM rate_events WHERE key=? AND event_type=? AND ts>?",
            (key, event_type, cutoff),
        ).fetchone()
        conn.close()
        return row[0] if row else 0

    def record(self, key: str, event_type: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO rate_events (key, event_type, ts) VALUES (?,?,?)",
                      (key, event_type, time.time()))
        conn.execute("DELETE FROM rate_events WHERE ts < ?", (time.time() - 86400,))
        conn.commit()
        conn.close()

    def check_post(self, agent: str) -> dict:
        c = self._count(agent, "post", 3600)
        ok = c < RATE_LIMIT_POSTS_PER_HOUR
        return {"allowed": ok, "count": c, "limit": RATE_LIMIT_POSTS_PER_HOUR,
                "retry_after": 3600 if not ok else None}

    def check_comment(self, agent: str) -> dict:
        c = self._count(agent, "comment", 3600)
        ok = c < RATE_LIMIT_COMMENTS_PER_HOUR
        return {"allowed": ok, "count": c, "limit": RATE_LIMIT_COMMENTS_PER_HOUR,
                "retry_after": 3600 if not ok else None}

    def check_ip(self, ip: str) -> dict:
        c = self._count(ip, "request", 60)
        ok = c < RATE_LIMIT_REQUESTS_PER_MINUTE
        return {"allowed": ok, "count": c, "limit": RATE_LIMIT_REQUESTS_PER_MINUTE,
                "retry_after": 60 if not ok else None}
