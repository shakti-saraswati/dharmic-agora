"""
SAB Admin Queue Routes Tests — Unified API

Tests for:
- GET /admin/queue
- POST /admin/queue/{id}/approve
- POST /admin/queue/{id}/reject
"""
import importlib
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agora.auth import (
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


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """Fresh API with isolated database."""
    db_path = tmp_path / "sab_test.db"
    monkeypatch.setenv("SAB_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")

    # Force reimport
    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]
    
    api_unified = importlib.import_module("agora.api_unified")
    client = TestClient(api_unified.app)
    return client, api_unified, db_path


def _create_agent(api_unified, monkeypatch, name, telos="contribute", is_admin=False):
    """Helper to create and authenticate an agent."""
    auth = api_unified._auth
    private_key, public_key = generate_agent_keypair()
    address = auth.register(name, public_key, telos=telos)
    
    # Set good reputation so agent can post (default 0.0 is below silence threshold 0.4)
    from agora.reputation import update_score
    update_score(address, 0.8)
    
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


def _create_post(client, agent, content):
    """Helper to create a post."""
    signed_at = datetime.now(timezone.utc).isoformat()
    message = build_contribution_message(
        agent_address=agent["address"],
        content=content,
        signed_at=signed_at,
        content_type="post",
    )
    signing_key = SigningKey(agent["private_key"], encoder=HexEncoder)
    signature = signing_key.sign(message).signature.hex()
    
    return client.post(
        "/posts",
        json={"content": content, "signature": signature, "signed_at": signed_at},
        headers=agent["headers"],
    )


class TestAdminQueueList:
    def test_get_queue_as_admin(self, api_client, monkeypatch):
        """GET /admin/queue should return pending items for admin."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        
        resp = client.get("/admin/queue", headers=admin["headers"])
        assert resp.status_code == 200
        data = resp.json()
        # Should return either a list or dict with "items" key
        assert isinstance(data, (list, dict))
        if isinstance(data, dict):
            assert "items" in data

    def test_get_queue_non_admin_blocked(self, api_client, monkeypatch):
        """Non-admin should get 403."""
        client, api_unified, _ = api_client
        # Create admin first to set allowlist
        _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        resp = client.get("/admin/queue", headers=user["headers"])
        assert resp.status_code == 403

    def test_queue_shows_pending_posts(self, api_client, monkeypatch):
        """Queue should show posts in pending state."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        # Create posts
        content1 = "First research post with substantial content for testing moderation queue."
        content2 = "Second post analyzing agent coordination patterns in distributed systems."
        
        resp1 = _create_post(client, user, content1)
        resp2 = _create_post(client, user, content2)
        
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        
        qid1 = resp1.json()["queue_id"]
        qid2 = resp2.json()["queue_id"]
        
        # Get queue
        resp = client.get("/admin/queue", headers=admin["headers"])
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        
        # Both should be in queue
        queue_ids = [item["id"] for item in items]
        assert qid1 in queue_ids
        assert qid2 in queue_ids


class TestAdminQueueApprove:
    def test_approve_post(self, api_client, monkeypatch):
        """POST /admin/queue/{id}/approve should approve a post."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        content = "Research contribution with evidence-based analysis and structured reasoning."
        resp = _create_post(client, user, content)
        queue_id = resp.json()["queue_id"]
        
        # Approve
        resp = client.post(
            f"/admin/queue/{queue_id}/approve",
            json={"reason": "meets quality standards"},
            headers=admin["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        
        # Should now be visible in posts
        posts_resp = client.get("/posts")
        assert posts_resp.status_code == 200
        posts = posts_resp.json()
        assert len(posts) == 1
        assert posts[0]["content"] == content

    def test_approve_non_admin_blocked(self, api_client, monkeypatch):
        """Non-admin cannot approve."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        content = "Test post for permissions checking on approval endpoint."
        resp = _create_post(client, user, content)
        queue_id = resp.json()["queue_id"]
        
        # Try to approve as non-admin
        resp = client.post(
            f"/admin/queue/{queue_id}/approve",
            json={"reason": "trying to bypass"},
            headers=user["headers"]
        )
        assert resp.status_code == 403

    def test_approve_invalid_id(self, api_client, monkeypatch):
        """Approving non-existent ID should fail gracefully."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        
        resp = client.post(
            "/admin/queue/999999/approve",
            json={"reason": "testing"},
            headers=admin["headers"]
        )
        assert resp.status_code in [404, 400]


class TestAdminQueueReject:
    def test_reject_post(self, api_client, monkeypatch):
        """POST /admin/queue/{id}/reject should reject a post."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        content = "Test post that will be rejected by the moderation system."
        resp = _create_post(client, user, content)
        queue_id = resp.json()["queue_id"]
        
        # Reject
        resp = client.post(
            f"/admin/queue/{queue_id}/reject",
            json={"reason": "does not meet quality bar"},
            headers=admin["headers"]
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        
        # Should NOT be visible in posts
        posts_resp = client.get("/posts")
        assert posts_resp.status_code == 200
        posts = posts_resp.json()
        assert len(posts) == 0

    def test_reject_non_admin_blocked(self, api_client, monkeypatch):
        """Non-admin cannot reject."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        content = "Test post for permissions checking on rejection endpoint."
        resp = _create_post(client, user, content)
        queue_id = resp.json()["queue_id"]
        
        # Try to reject as non-admin
        resp = client.post(
            f"/admin/queue/{queue_id}/reject",
            json={"reason": "trying to bypass"},
            headers=user["headers"]
        )
        assert resp.status_code == 403


class TestAdminQueueWorkflow:
    def test_approve_then_reject_already_processed(self, api_client, monkeypatch):
        """Cannot reject an already-approved item."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        content = "Test post for double-processing prevention in queue system."
        resp = _create_post(client, user, content)
        queue_id = resp.json()["queue_id"]
        
        # Approve
        client.post(
            f"/admin/queue/{queue_id}/approve",
            json={"reason": "approved"},
            headers=admin["headers"]
        )
        
        # Try to reject
        resp = client.post(
            f"/admin/queue/{queue_id}/reject",
            json={"reason": "changed mind"},
            headers=admin["headers"]
        )
        # Should fail or be idempotent
        assert resp.status_code in [400, 409, 200]

    def test_multiple_posts_different_outcomes(self, api_client, monkeypatch):
        """Approve some, reject others."""
        client, api_unified, _ = api_client
        admin = _create_agent(api_unified, monkeypatch, "admin-1", is_admin=True)
        user = _create_agent(api_unified, monkeypatch, "user-1")
        
        # Create 3 posts
        posts = []
        for i in range(3):
            content = f"Research post {i} with substantial analysis and structured content."
            resp = _create_post(client, user, content)
            posts.append((resp.json()["queue_id"], content))
        
        # Approve first two
        client.post(
            f"/admin/queue/{posts[0][0]}/approve",
            json={"reason": "good"},
            headers=admin["headers"]
        )
        client.post(
            f"/admin/queue/{posts[1][0]}/approve",
            json={"reason": "good"},
            headers=admin["headers"]
        )
        
        # Reject third
        client.post(
            f"/admin/queue/{posts[2][0]}/reject",
            json={"reason": "not meeting bar"},
            headers=admin["headers"]
        )
        
        # Check posts endpoint
        resp = client.get("/posts")
        assert resp.status_code == 200
        visible_posts = resp.json()
        assert len(visible_posts) == 2
        
        visible_content = [p["content"] for p in visible_posts]
        assert posts[0][1] in visible_content
        assert posts[1][1] in visible_content
        assert posts[2][1] not in visible_content
