"""
SAB Data Integrity Tests -- Sprint 2 API + schema hardening.

Validates:
- models.py dataclass completeness (Post, Vote, GateEvidence)
- db.py importability with fixed models
- _serialize_spark_row nullable field guards
- _load_gate_scores edge cases
- Web form error recovery paths
- Gate evidence nullable JSON handling
"""
import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder

    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False


# =========================================================================
# Model integrity
# =========================================================================


class TestModelCompleteness:
    """Verify all models referenced by db.py and __init__.py exist."""

    def test_post_dataclass_exists(self):
        from agora.models import Post

        p = Post(
            id="abc123",
            author_address="addr_test",
            content="hello",
            created_at="2026-01-01T00:00:00+00:00",
            gate_evidence_hash="deadbeef",
        )
        assert p.id == "abc123"
        assert p.karma == 0
        assert p.comment_count == 0
        assert p.is_deleted == 0
        assert p.signature is None

    def test_vote_dataclass_exists(self):
        from agora.models import Vote, VoteType

        v = Vote(
            id="v123",
            voter_address="addr_voter",
            content_id="post_abc",
            vote_type=VoteType.UP,
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert v.vote_type == VoteType.UP

    def test_gate_evidence_dataclass_exists(self):
        from agora.models import GateEvidence

        ge = GateEvidence(
            content_id="post_abc",
            evidence_hash="aabbcc",
            evidence_json='{"gate": "SATYA"}',
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert ge.content_id == "post_abc"

    def test_db_module_importable(self):
        """db.py should import without errors now that models are complete."""
        mod = importlib.import_module("agora.db")
        assert hasattr(mod, "AgoraDB")
        assert hasattr(mod, "get_db")

    def test_init_exports_post_vote(self):
        """__init__.py lazy exports should resolve Post and Vote."""
        import agora

        assert hasattr(agora, "Post")
        assert hasattr(agora, "Vote")
        assert hasattr(agora, "GateEvidence")
        assert hasattr(agora, "ContentType")
        assert hasattr(agora, "VoteType")


# =========================================================================
# Nullable field guards in app.py
# =========================================================================


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    """Isolated app module with fresh DB."""
    db_path = tmp_path / "spark.db"
    monkeypatch.setenv("SAB_SPARK_DB_PATH", str(db_path))

    for mod_name in list(sys.modules):
        if mod_name.startswith("agora."):
            del sys.modules[mod_name]
    mod = importlib.import_module("agora.app")
    mod.init_db()
    return mod


class TestSerializeSparkRow:
    """_serialize_spark_row should handle NULL/missing values gracefully."""

    def test_empty_gate_scores(self, app_module):
        """Empty-string gate_scores column should produce empty dimensions, not crash."""
        conn = sqlite3.connect(app_module.SPARK_DB)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO sparks (content, content_type, author_id, created_at, gate_scores, status, rv_contraction, composite_score)
            VALUES ('test', 'text', 'agent1', '2026-01-01', '', 'spark', NULL, NULL)
            """
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sparks ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        result = app_module._serialize_spark_row(row)
        assert result["content"] == "test"
        assert result["gate_scores"] == {"dimensions": {}, "composite": 0.0}
        assert result["composite_score"] == 0.0
        assert result["rv_contraction"] is None

    def test_corrupt_gate_scores_json(self, app_module):
        """Corrupt JSON in gate_scores should fall back to empty dict."""
        conn = sqlite3.connect(app_module.SPARK_DB)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO sparks (content, content_type, author_id, created_at, gate_scores, status, rv_contraction, composite_score)
            VALUES ('test2', 'text', 'agent2', '2026-01-01', 'NOT_JSON{{{', 'spark', NULL, 0.5)
            """
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sparks ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        result = app_module._serialize_spark_row(row)
        assert result["gate_scores"] == {"dimensions": {}, "composite": 0.0}
        assert result["composite_score"] == 0.5


class TestLoadGateScores:
    """_load_gate_scores handles edge cases."""

    def test_valid_json(self, app_module):
        result = app_module._load_gate_scores('{"dimensions": {"satya": {"score": 0.9}}, "composite": 0.8}')
        assert result["composite"] == 0.8
        assert "satya" in result["dimensions"]

    def test_empty_string(self, app_module):
        result = app_module._load_gate_scores("")
        assert result == {"dimensions": {}, "composite": 0.0}

    def test_none_string(self, app_module):
        result = app_module._load_gate_scores("None")
        assert result == {"dimensions": {}, "composite": 0.0}

    def test_non_dict_json(self, app_module):
        result = app_module._load_gate_scores('"just a string"')
        assert result == {"dimensions": {}, "composite": 0.0}

    def test_list_json(self, app_module):
        result = app_module._load_gate_scores("[1, 2, 3]")
        assert result == {"dimensions": {}, "composite": 0.0}


# =========================================================================
# Web surface form flows
# =========================================================================


@pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
class TestWebFormFlows:
    """Test web form submission and error recovery."""

    @pytest.fixture
    def web_client(self, tmp_path, monkeypatch):
        db_path = tmp_path / "spark.db"
        monkeypatch.setenv("SAB_SPARK_DB_PATH", str(db_path))

        for mod_name in list(sys.modules):
            if mod_name.startswith("agora."):
                del sys.modules[mod_name]
        mod = importlib.import_module("agora.app")
        mod.init_db()

        from fastapi.testclient import TestClient

        return TestClient(mod.app), mod

    def test_submit_empty_content_returns_400(self, web_client):
        """Empty content submission returns 400 with error message."""
        client, _ = web_client
        resp = client.post(
            "/submit", data={"content": "   ", "display_name": "tester"}, follow_redirects=False
        )
        assert resp.status_code == 400
        assert "Content is required" in resp.text

    def test_submit_valid_spark_redirects(self, web_client):
        """Valid content submission redirects to spark detail."""
        client, _ = web_client
        resp = client.post(
            "/submit",
            data={"content": "A valid test spark with enough substance.", "display_name": "tester"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "/spark/" in resp.headers.get("location", "")

    def test_challenge_empty_content_redirects(self, web_client):
        """Empty challenge content redirects with error param."""
        client, mod = web_client
        # First create a spark
        resp = client.post(
            "/submit",
            data={"content": "Spark for challenge test content here.", "display_name": "author"},
            follow_redirects=False,
        )
        location = resp.headers.get("location", "")
        spark_id = location.split("/spark/")[1].split("?")[0] if "/spark/" in location else "1"

        # Extract CSRF token from active session
        csrf_token = ""
        for _, session_data in mod._WEB_SESSIONS.items():
            csrf_token = session_data.get("csrf_token", "")
            if csrf_token:
                break

        # Challenge with whitespace-only content
        resp = client.post(
            f"/spark/{spark_id}/challenge",
            data={"content": "   ", "display_name": "challenger", "_csrf": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "challenge_error=1" in resp.headers.get("location", "")

    def test_register_creates_session(self, web_client):
        """Register creates session and redirects to agent profile."""
        client, _ = web_client
        resp = client.post(
            "/register", data={"display_name": "new-agent"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert "/agent/" in resp.headers.get("location", "")

    def test_feed_renders_without_sparks(self, web_client):
        """Homepage renders cleanly with empty DB."""
        client, _ = web_client
        resp = client.get("/")
        assert resp.status_code == 200
        assert "SAB" in resp.text

    def test_canon_feed_renders(self, web_client):
        """Canon feed renders without errors."""
        client, _ = web_client
        resp = client.get("/canon")
        assert resp.status_code == 200

    def test_compost_feed_renders(self, web_client):
        """Compost feed renders without errors."""
        client, _ = web_client
        resp = client.get("/compost")
        assert resp.status_code == 200

    def test_about_page_renders(self, web_client):
        """About page renders without errors."""
        client, _ = web_client
        resp = client.get("/about")
        assert resp.status_code == 200

    def test_submit_page_get(self, web_client):
        """GET /submit renders the form."""
        client, _ = web_client
        resp = client.get("/submit")
        assert resp.status_code == 200
        assert "Submit" in resp.text

    def test_register_page_get(self, web_client):
        """GET /register renders the form."""
        client, _ = web_client
        resp = client.get("/register")
        assert resp.status_code == 200

    def test_spark_detail_nonexistent(self, web_client):
        """Accessing nonexistent spark returns 404."""
        client, _ = web_client
        resp = client.get("/spark/99999")
        assert resp.status_code == 404

    def test_witness_on_valid_spark(self, web_client):
        """Witness attestation on a valid spark succeeds."""
        client, mod = web_client
        # Create a spark first
        resp = client.post(
            "/submit",
            data={"content": "Spark for witness testing content.", "display_name": "author2"},
            follow_redirects=False,
        )
        location = resp.headers.get("location", "")
        spark_id = location.split("/spark/")[1].split("?")[0] if "/spark/" in location else "1"

        # Extract CSRF token
        csrf_token = ""
        for _, session_data in mod._WEB_SESSIONS.items():
            csrf_token = session_data.get("csrf_token", "")
            if csrf_token:
                break

        # Witness affirm (with CSRF)
        resp = client.post(
            f"/spark/{spark_id}/witness",
            data={"action": "affirm", "note": "Good spark", "display_name": "witness1", "_csrf": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "#timeline" in resp.headers.get("location", "")

    def test_spark_detail_full_flow(self, web_client):
        """Submit -> view detail -> challenge -> witness full lifecycle.

        CSRF tokens are required after the first session-creating request.
        We extract the csrf_token from the session to pass on subsequent
        mutating requests.
        """
        client, mod = web_client

        # Submit (creates session)
        resp = client.post(
            "/submit",
            data={"content": "Full lifecycle test content.", "display_name": "lifecycle"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers.get("location", "")
        spark_id = location.split("/spark/")[1].split("?")[0]

        # Extract CSRF token from the active session
        csrf_token = ""
        for token_val, session_data in mod._WEB_SESSIONS.items():
            csrf_token = session_data.get("csrf_token", "")
            if csrf_token:
                break

        # View detail
        resp = client.get(f"/spark/{spark_id}")
        assert resp.status_code == 200
        assert "Full lifecycle" in resp.text

        # Challenge (with CSRF)
        resp = client.post(
            f"/spark/{spark_id}/challenge",
            data={"content": "I challenge this spark on grounds of clarity.", "display_name": "critic", "_csrf": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Witness compost (with CSRF)
        resp = client.post(
            f"/spark/{spark_id}/witness",
            data={"action": "compost", "note": "Not up to standard", "display_name": "judge", "_csrf": csrf_token},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Verify status changed to compost on detail page
        resp = client.get(f"/spark/{spark_id}")
        assert resp.status_code == 200
        assert "compost" in resp.text.lower()


# =========================================================================
# API endpoint data integrity (api_server.py)
# =========================================================================


@pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
class TestApiServerDataIntegrity:
    """Test api_server.py endpoints handle edge cases."""

    @pytest.fixture
    def api_client(self, tmp_path, monkeypatch):
        db_path = tmp_path / "sab_test.db"
        shadow_summary = tmp_path / "shadow_loop" / "run_summary.json"
        shadow_summary.parent.mkdir(parents=True, exist_ok=True)
        shadow_summary.write_text(
            json.dumps(
                {
                    "timestamp": "2026-02-16T00:00:00+00:00",
                    "status": "stable",
                    "alert_count": 0,
                    "high_alert_count": 0,
                }
            )
        )
        monkeypatch.setenv("SAB_DB_PATH", str(db_path))
        monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")
        monkeypatch.setenv("SAB_SHADOW_SUMMARY_PATH", str(shadow_summary))

        for mod_name in list(sys.modules):
            if mod_name.startswith("agora."):
                del sys.modules[mod_name]
        api_server = importlib.import_module("agora.api_server")

        from fastapi.testclient import TestClient

        return TestClient(api_server.app), api_server

    def test_status_endpoint(self, api_client):
        """Status endpoint returns valid data."""
        client, _ = api_client
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_gates_endpoint(self, api_client):
        """Gates endpoint returns dimension info."""
        client, _ = api_client
        resp = client.get("/gates")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_dimensions" in data
        assert "dimensions" in data

    def test_post_not_found(self, api_client):
        """Getting nonexistent post returns 404."""
        client, _ = api_client
        resp = client.get("/posts/99999")
        assert resp.status_code == 404

    def test_audit_trail_empty(self, api_client):
        """Audit trail returns empty list on fresh DB."""
        client, _ = api_client
        resp = client.get("/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_posts_list_empty(self, api_client):
        """Posts list returns empty on fresh DB."""
        client, _ = api_client
        resp = client.get("/posts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_witness_chain_info(self, api_client):
        """Witness chain endpoint returns metadata."""
        client, _ = api_client
        resp = client.get("/witness/chain")
        assert resp.status_code == 200
        data = resp.json()
        assert "entry_count" in data

    def test_register_simple_agent(self, api_client):
        """Simple registration creates agent."""
        client, _ = api_client
        resp = client.post("/auth/register", json={"name": "test-agent", "telos": "testing"})
        assert resp.status_code == 200
        data = resp.json()
        assert "address" in data
        assert "token" in data

    def test_register_duplicate_name_rejected(self, api_client):
        """Registering with the same name is correctly rejected."""
        client, _ = api_client
        resp1 = client.post("/auth/register", json={"name": "dup-agent", "telos": "t1"})
        assert resp1.status_code == 200
        resp2 = client.post("/auth/register", json={"name": "dup-agent", "telos": "t2"})
        assert resp2.status_code == 400

    def test_post_requires_auth(self, api_client):
        """Creating post without auth returns 401."""
        client, _ = api_client
        resp = client.post("/posts", json={"content": "test post"})
        assert resp.status_code == 401
