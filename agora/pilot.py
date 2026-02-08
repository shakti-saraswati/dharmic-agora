"""
SAB 20-Agent Pilot Infrastructure — invite codes, cohorts, surveys, metrics.
"""
import secrets
import sqlite3
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict


class PilotManager:
    """Manages invite codes, cohort tagging, surveys, and pilot metrics."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init()

    def _init(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                code TEXT PRIMARY KEY,
                cohort TEXT NOT NULL DEFAULT 'gated',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                redeemed_by TEXT,
                redeemed_at TEXT,
                created_by TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_cohorts (
                agent_address TEXT PRIMARY KEY,
                cohort TEXT NOT NULL,
                joined_at TEXT NOT NULL,
                invite_code TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_address TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT 'v1',
                answers TEXT NOT NULL,
                submitted_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def create_invite(self, cohort: str, created_by: str,
                      expires_hours: int = 168) -> dict:
        """Create an invite code. Returns {code, cohort, expires_at}."""
        code = secrets.token_urlsafe(12)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=expires_hours)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO invite_codes (code, cohort, created_at, expires_at, created_by) VALUES (?,?,?,?,?)",
            (code, cohort, now.isoformat(), expires.isoformat(), created_by),
        )
        conn.commit()
        conn.close()
        return {"code": code, "cohort": cohort, "expires_at": expires.isoformat()}

    def redeem_invite(self, code: str, agent_address: str) -> dict:
        """Redeem an invite code. Returns cohort info or raises ValueError."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM invite_codes WHERE code=?", (code,)).fetchone()
        if not row:
            conn.close()
            raise ValueError("Invalid invite code")
        row = dict(row)
        if row["redeemed_by"]:
            conn.close()
            raise ValueError("Invite already redeemed")
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            conn.close()
            raise ValueError("Invite expired")

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE invite_codes SET redeemed_by=?, redeemed_at=? WHERE code=?",
                      (agent_address, now, code))
        conn.execute(
            "INSERT OR REPLACE INTO agent_cohorts (agent_address, cohort, joined_at, invite_code) VALUES (?,?,?,?)",
            (agent_address, row["cohort"], now, code),
        )
        conn.commit()
        conn.close()
        return {"cohort": row["cohort"], "agent_address": agent_address}

    def get_cohort(self, agent_address: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT cohort FROM agent_cohorts WHERE agent_address=?",
            (agent_address,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def submit_survey(self, agent_address: str, answers: dict,
                      version: str = "v1") -> int:
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "INSERT INTO surveys (agent_address, version, answers, submitted_at) VALUES (?,?,?,?)",
            (agent_address, version, json.dumps(answers), now),
        )
        sid = cur.lastrowid
        conn.commit()
        conn.close()
        return sid

    def list_invites(self, limit: int = 100) -> List[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM invite_codes ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def pilot_metrics(self, db_path: Optional[Path] = None) -> dict:
        """Generate daily pilot metrics."""
        p = db_path or self.db_path
        conn = sqlite3.connect(p)

        # Cohort counts
        cohorts = {}
        for row in conn.execute("SELECT cohort, COUNT(*) FROM agent_cohorts GROUP BY cohort").fetchall():
            cohorts[row[0]] = row[1]

        # Posts by status
        try:
            statuses = {}
            for row in conn.execute("SELECT status, COUNT(*) FROM moderation_queue GROUP BY status").fetchall():
                statuses[row[0]] = row[1]
        except Exception:
            statuses = {}

        # Total surveys
        survey_count = conn.execute("SELECT COUNT(*) FROM surveys").fetchone()[0]

        conn.close()
        return {
            "cohorts": cohorts,
            "moderation_statuses": statuses,
            "surveys_submitted": survey_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
