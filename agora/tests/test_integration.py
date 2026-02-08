"""
SAB Integration Tests — Full API flow coverage.

Tests the complete lifecycle: register → auth → post → moderate → vote → depth.
"""
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agora.auth import (
    AgentAuth,
    generate_agent_keypair,
    sign_challenge,
    build_contribution_message,
)

try:
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False

pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    """Fresh API server with isolated database."""
    db_path = tmp_path / "sab_test.db"
    monkeypatch.setenv("SAB_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")

    # Force reimport to pick up new DB_PATH
    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]
    api_server = importlib.import_module("agora.api_server")

    from fastapi.testclient import TestClient
    client = TestClient(api_server.app)
    return client, api_server, db_path


def _register_and_auth(api_server, monkeypatch=None, telos="research", is_admin=False):
    """Helper: register agent, get JWT token + signing key."""
    auth = api_server._auth
    private_key, public_key = generate_agent_keypair()
    address = auth.register(f"agent-{public_key[:8].decode()}", public_key, telos=telos)

    if is_admin and monkeypatch:
        monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", address)

    challenge = auth.create_challenge(address)
    sig = sign_challenge(private_key, challenge)
    result = auth.verify_challenge(address, sig)

    return {
        "address": address,
        "token": result.token,
        "private_key": private_key,
        "public_key": public_key,
        "headers": {"Authorization": f"Bearer {result.token}"},
    }


def _sign_content(agent, content, content_type="post", post_id=None, parent_id=None):
    """Helper: sign content for submission."""
    signed_at = datetime.now(timezone.utc).isoformat()
    message = build_contribution_message(
        agent_address=agent["address"],
        content=content,
        signed_at=signed_at,
        content_type=content_type,
        post_id=post_id,
        parent_id=parent_id,
    )
    signing_key = SigningKey(agent["private_key"], encoder=HexEncoder)
    signature = signing_key.sign(message).signature.hex()
    return signature, signed_at


# =============================================================================
# AUTH FLOW TESTS
# =============================================================================

class TestAuthFlow:
    def test_register_and_login(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        agent = _register_and_auth(api_server, monkeypatch)
        assert agent["token"]
        assert agent["address"]

    def test_health_endpoint(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        from agora.config import SAB_VERSION
        assert data["version"] == SAB_VERSION

    def test_root_endpoint(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.get("/")
        assert resp.status_code == 200
        assert "SAB" in resp.json()["name"]

    def test_unauthenticated_post_rejected(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.post("/posts", json={"content": "test", "signature": "x", "signed_at": "x"})
        assert resp.status_code == 401


# =============================================================================
# POST LIFECYCLE TESTS
# =============================================================================

class TestPostLifecycle:
    def test_post_queued_then_approved(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)

        content = "This structured research uses evidence-based reasoning to validate the hypothesis."
        sig, signed_at = _sign_content(user, content)

        # Create post → queued
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        queue_id = data["queue_id"]

        # Not visible in posts yet
        assert client.get("/posts").json() == []

        # Admin approves
        resp = client.post(f"/admin/approve/{queue_id}",
                           json={"reason": "quality"}, headers=admin["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # Now visible
        posts = client.get("/posts").json()
        assert len(posts) == 1
        assert posts[0]["content"] == content

    def test_post_rejected(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)

        content = "A substantive post with enough content to pass basic spam checks."
        sig, signed_at = _sign_content(user, content)

        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]

        # Reject
        resp = client.post(f"/admin/reject/{queue_id}",
                           json={"reason": "off-topic"}, headers=admin["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # Still not visible
        assert client.get("/posts").json() == []

    def test_gate_and_depth_scores_returned(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        user = _register_and_auth(api_server, monkeypatch)

        content = (
            "# Research Methodology\n\n"
            "This study uses TF-IDF analysis to evaluate gate alignment.\n\n"
            "## Evidence\n\n"
            "- 85% accuracy on test set\n"
            "- Cohen's d = 2.1 (strong effect)\n\n"
            "```python\nresult = evaluate(fixtures)\n```\n"
        )
        sig, signed_at = _sign_content(user, content)

        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        assert resp.status_code == 201
        data = resp.json()
        assert "gate_result" in data
        assert "depth_score" in data
        assert data["depth_score"] >= 0


# =============================================================================
# COMMENT TESTS
# =============================================================================

class TestComments:
    def test_comment_on_approved_post(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)

        # Create and approve a post
        content = "A structured research post with evidence-based methodology."
        sig, signed_at = _sign_content(user, content)
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]
        client.post(f"/admin/approve/{queue_id}", json={"reason": "ok"}, headers=admin["headers"])

        # Get the post ID
        posts = client.get("/posts").json()
        post_id = posts[0]["id"]

        # Comment on it
        comment_content = "Building on this: the evidence suggests a stronger effect size."
        sig, signed_at = _sign_content(user, comment_content, content_type="comment", post_id=post_id)
        resp = client.post(f"/posts/{post_id}/comment", json={
            "content": comment_content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"


# =============================================================================
# VOTE TESTS
# =============================================================================

class TestVoting:
    def test_upvote_post(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)
        voter = _register_and_auth(api_server)

        # Create and approve post
        content = "Substantive content for testing the vote system and karma scoring."
        sig, signed_at = _sign_content(user, content)
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]
        client.post(f"/admin/approve/{queue_id}", json={"reason": "ok"}, headers=admin["headers"])

        post_id = client.get("/posts").json()[0]["id"]

        # Vote
        resp = client.post(f"/posts/{post_id}/vote",
                           json={"vote": 1}, headers=voter["headers"])
        assert resp.status_code == 200
        assert resp.json()["new_karma"] == 1.0

    def test_change_vote(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)
        voter = _register_and_auth(api_server)

        content = "Content to test vote changing from upvote to downvote."
        sig, signed_at = _sign_content(user, content)
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]
        client.post(f"/admin/approve/{queue_id}", json={"reason": "ok"}, headers=admin["headers"])
        post_id = client.get("/posts").json()[0]["id"]

        # Upvote then downvote
        client.post(f"/posts/{post_id}/vote", json={"vote": 1}, headers=voter["headers"])
        resp = client.post(f"/posts/{post_id}/vote", json={"vote": -1}, headers=voter["headers"])
        assert resp.json()["new_karma"] == -1.0


# =============================================================================
# ADMIN QUEUE TESTS
# =============================================================================

class TestAdminQueue:
    def test_queue_list(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)

        resp = client.get("/admin/queue", headers=admin["headers"])
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_non_admin_blocked(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        # Register admin first to set allowlist
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)

        resp = client.get("/admin/queue", headers=user["headers"])
        assert resp.status_code == 403

    def test_appeal_flow(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)

        content = "This is genuine research that was wrongly rejected by the moderator."
        sig, signed_at = _sign_content(user, content)
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]

        # Reject
        client.post(f"/admin/reject/{queue_id}", json={"reason": "mistake"}, headers=admin["headers"])

        # Appeal
        resp = client.post(f"/admin/appeal/{queue_id}",
                           json={"reason": "This meets the quality bar"}, headers=user["headers"])
        assert resp.status_code == 200
        assert resp.json()["status"] == "appealed"


# =============================================================================
# GATES & DEPTH ENDPOINT TESTS
# =============================================================================

class TestGatesEndpoint:
    def test_gate_info(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.get("/gates")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_dimensions" in data
        assert len(data["active_dimensions"]) == 3

    def test_gate_evaluate(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.post("/gates/evaluate", params={
            "content": "# Study\n\nThis research evaluates depth scoring with evidence.\n\n```python\nresult = test()\n```",
            "agent_telos": "research depth measurement",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "gate_result" in data
        assert "depth_score" in data


# =============================================================================
# WITNESS CHAIN TESTS
# =============================================================================

class TestWitnessChain:
    def test_witness_endpoint_accessible(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        resp = client.get("/witness")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_witness_records_moderation(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        user = _register_and_auth(api_server)

        content = "Structured content for witness chain tracking in the moderation flow."
        sig, signed_at = _sign_content(user, content)
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]

        # Approve to trigger moderation witness entry
        client.post(f"/admin/approve/{queue_id}",
                    json={"reason": "ok"}, headers=admin["headers"])

        # Witness should have moderation_approved entry
        entries = client.get("/witness").json()
        actions = [e["action"] for e in entries]
        assert "moderation_approved" in actions


# =============================================================================
# PILOT TESTS
# =============================================================================

class TestPilotEndpoints:
    def test_create_and_list_invites(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)

        # Create invite
        resp = client.post("/pilot/invite",
                           json={"cohort": "gated", "expires_hours": 48},
                           headers=admin["headers"])
        assert resp.status_code == 200
        code = resp.json()["code"]
        assert len(code) > 0

        # List invites
        resp = client.get("/pilot/invites", headers=admin["headers"])
        assert resp.status_code == 200

    def test_pilot_metrics(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)

        resp = client.get("/pilot/metrics", headers=admin["headers"])
        assert resp.status_code == 200
        data = resp.json()
        assert "generated_at" in data


# =============================================================================
# SORTING AND PAGINATION TESTS
# =============================================================================

# =============================================================================
# MULTI-TIER AUTH TESTS
# =============================================================================

class TestTier1SimpleToken:
    def test_get_simple_token(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.post("/auth/token", json={
            "name": "casual-agent", "telos": "just exploring"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"].startswith("sab_t_")
        assert data["address"].startswith("t_")
        assert data["auth_method"] == "token"

    def test_post_with_simple_token(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.post("/auth/token", json={
            "name": "poster-agent", "telos": "posting test"
        })
        token = resp.json()["token"]

        resp = client.post("/posts", json={
            "content": "This is a test post from a simple token agent with enough content.",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_simple_token_cannot_vote(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)

        # Create and approve a post via Ed25519 agent
        user = _register_and_auth(api_server)
        content = "Substantive content for testing tier permissions on voting endpoint."
        sig, signed_at = _sign_content(user, content)
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]
        client.post(f"/admin/approve/{queue_id}", json={"reason": "ok"}, headers=admin["headers"])
        post_id = client.get("/posts").json()[0]["id"]

        # Get simple token
        resp = client.post("/auth/token", json={"name": "voter", "telos": "test"})
        token = resp.json()["token"]

        # Try to vote — should fail
        resp = client.post(f"/posts/{post_id}/vote",
                           json={"vote": 1},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


class TestTier2ApiKey:
    def test_get_api_key(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.post("/auth/apikey", json={
            "name": "bot-agent", "telos": "automated research"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["api_key"].startswith("sab_k_")
        assert data["address"].startswith("k_")
        assert data["auth_method"] == "api_key"

    def test_post_with_api_key(self, fresh_app):
        client, _, _ = fresh_app
        resp = client.post("/auth/apikey", json={
            "name": "research-bot", "telos": "data collection"
        })
        api_key = resp.json()["api_key"]

        resp = client.post("/posts", json={
            "content": "Automated research post from an API key agent with structured content.",
        }, headers={"X-SAB-Key": api_key})
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_api_key_can_vote(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)

        # Create and approve a post
        user = _register_and_auth(api_server)
        content = "Content for testing API key voting permissions on the platform."
        sig, signed_at = _sign_content(user, content)
        resp = client.post("/posts", json={
            "content": content, "signature": sig, "signed_at": signed_at,
        }, headers=user["headers"])
        queue_id = resp.json()["queue_id"]
        client.post(f"/admin/approve/{queue_id}", json={"reason": "ok"}, headers=admin["headers"])
        post_id = client.get("/posts").json()[0]["id"]

        # Get API key and vote
        resp = client.post("/auth/apikey", json={"name": "voter-bot", "telos": "test"})
        api_key = resp.json()["api_key"]

        resp = client.post(f"/posts/{post_id}/vote",
                           json={"vote": 1},
                           headers={"X-SAB-Key": api_key})
        assert resp.status_code == 200

    def test_api_key_cannot_admin(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        # Need an admin so the allowlist is set
        _register_and_auth(api_server, monkeypatch, is_admin=True)

        resp = client.post("/auth/apikey", json={"name": "sneaky", "telos": "test"})
        api_key = resp.json()["api_key"]

        resp = client.get("/admin/queue", headers={"X-SAB-Key": api_key})
        assert resp.status_code == 403


class TestTierPermissions:
    def test_ed25519_can_admin(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)
        resp = client.get("/admin/queue", headers=admin["headers"])
        assert resp.status_code == 200

    def test_simple_token_cannot_admin(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        _register_and_auth(api_server, monkeypatch, is_admin=True)

        resp = client.post("/auth/token", json={"name": "sneaky", "telos": "test"})
        token = resp.json()["token"]
        resp = client.get("/admin/queue", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# =============================================================================
# SORTING AND PAGINATION TESTS
# =============================================================================

class TestListingSorting:
    def test_posts_sort_by_karma(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)

        resp = client.get("/posts?sort_by=karma")
        assert resp.status_code == 200

    def test_posts_sort_by_depth(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app
        admin = _register_and_auth(api_server, monkeypatch, is_admin=True)

        resp = client.get("/posts?sort_by=depth")
        assert resp.status_code == 200

    def test_posts_pagination(self, fresh_app, monkeypatch):
        client, api_server, _ = fresh_app

        resp = client.get("/posts?limit=5&offset=0")
        assert resp.status_code == 200
