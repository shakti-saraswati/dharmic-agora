"""Test Pulse-001: Reputation Floor — SABP/1.0 seed element."""
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from agora.reputation import get_score, update_score, is_silenced, DEFAULT_PRIOR, SILENCE_THRESHOLD


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary DB with agents table."""
    db_path = tmp_path / "test_agora.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE agents (
            address TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            public_key_hex TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reputation REAL DEFAULT 0.0,
            telos TEXT DEFAULT '',
            last_seen TEXT,
            is_banned INTEGER DEFAULT 0
        )
    """)
    conn.execute(
        "INSERT INTO agents (address, name, public_key_hex, created_at, reputation) VALUES (?, ?, ?, ?, ?)",
        ("agent_good", "Good Agent", "aabbcc", "2026-01-01T00:00:00Z", 0.8)
    )
    conn.execute(
        "INSERT INTO agents (address, name, public_key_hex, created_at, reputation) VALUES (?, ?, ?, ?, ?)",
        ("agent_low", "Low Agent", "ddeeff", "2026-01-01T00:00:00Z", 0.1)
    )
    conn.commit()
    conn.close()
    return db_path


class TestGetScore:
    def test_unknown_agent_returns_default(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            assert get_score("agent_unknown") == DEFAULT_PRIOR

    def test_known_agent_returns_score(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            assert get_score("agent_good") == 0.8

    def test_low_agent_score(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            assert get_score("agent_low") == 0.1


class TestUpdateScore:
    def test_update_increases(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            new = update_score("agent_low", 1.0)
            # EMA: 0.1 * 0.8 + 1.0 * 0.2 = 0.28
            assert abs(new - 0.28) < 0.001

    def test_update_persists(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            update_score("agent_low", 1.0)
            assert abs(get_score("agent_low") - 0.28) < 0.001

    def test_score_clamped(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            new = update_score("agent_good", 1.0)
            assert 0.0 <= new <= 1.0


class TestIsSilenced:
    def test_low_rep_silenced(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            assert is_silenced("agent_low") is True

    def test_high_rep_not_silenced(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            assert is_silenced("agent_good") is False

    def test_unknown_agent_silenced(self, test_db):
        """Unknown agents have 0.0 rep — silenced by default."""
        with patch("agora.reputation.AGORA_DB", test_db):
            assert is_silenced("agent_unknown") is True

    def test_at_threshold_not_silenced(self, test_db):
        """Exactly at threshold = not silenced (strict <)."""
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO agents (address, name, public_key_hex, created_at, reputation) VALUES (?, ?, ?, ?, ?)",
            ("agent_boundary", "Boundary", "112233", "2026-01-01T00:00:00Z", SILENCE_THRESHOLD)
        )
        conn.commit()
        conn.close()
        with patch("agora.reputation.AGORA_DB", test_db):
            assert is_silenced("agent_boundary") is False

    def test_custom_threshold(self, test_db):
        with patch("agora.reputation.AGORA_DB", test_db):
            assert is_silenced("agent_good", threshold=0.9) is True
            assert is_silenced("agent_good", threshold=0.5) is False
