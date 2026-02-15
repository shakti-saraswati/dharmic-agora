"""
Reputation Floor — SABP/1.0 Seed Element #2
Bayesian reputation tracking. Agents below threshold are silenced.

Uses direct SQLite access to avoid broken import chain in db.py.
"""
import sqlite3
from pathlib import Path

AGORA_DB = Path(__file__).parent.parent / "data" / "agora.db"
DEFAULT_PRIOR = 0.0
SILENCE_THRESHOLD = 0.4


def _get_conn():
    """Get a SQLite connection to the agora database."""
    conn = sqlite3.connect(AGORA_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_score(agent_address: str) -> float:
    """Get current reputation score for agent. Returns DEFAULT_PRIOR if unknown."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT reputation FROM agents WHERE address = ?",
            (agent_address,)
        ).fetchone()
        if row is None or row["reputation"] is None:
            return DEFAULT_PRIOR
        return row["reputation"]
    finally:
        conn.close()


def update_score(agent_address: str, evidence_score: float) -> float:
    """
    Bayesian update: blend prior with new evidence.
    evidence_score: 0.0 (terrible) to 1.0 (excellent)
    Returns new score.
    """
    current = get_score(agent_address)
    alpha = 0.2
    new_score = current * (1 - alpha) + evidence_score * alpha
    new_score = max(0.0, min(1.0, new_score))

    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE agents SET reputation = ? WHERE address = ?",
            (new_score, agent_address)
        )
        conn.commit()
    finally:
        conn.close()
    return new_score


def is_silenced(agent_address: str, threshold: float = SILENCE_THRESHOLD) -> bool:
    """Agent is silenced if reputation below threshold."""
    return get_score(agent_address) < threshold
