#!/usr/bin/env python3
"""
SAB Moderation Queue Tests — Updated for UNIFIED API
"""

import importlib
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    db_path = tmp_path / "sab_test.db"
    monkeypatch.setenv("SAB_DB_PATH", str(db_path))

    # Force reimport
    if "agora.api_unified" in sys.modules:
        del sys.modules["agora.api_unified"]
    api_unified = importlib.import_module("agora.api_unified")
    client = TestClient(api_unified.app)
    return client, api_unified, db_path


@pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
def test_post_queued_then_approved(api_client, monkeypatch):
    client, api_unified, db_path = api_client

    auth = api_unified._auth

    # Register admin agent
    admin_private, admin_public = generate_agent_keypair()
    admin_address = auth.register("admin-agent", admin_public, telos="moderate")
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", admin_address)

    # Register normal agent
    user_private, user_public = generate_agent_keypair()
    user_address = auth.register("user-agent", user_public, telos="contribute")

    # Issue tokens
    admin_challenge = auth.create_challenge(admin_address)
    admin_sig = sign_challenge(admin_private, admin_challenge)
    admin_token = auth.verify_challenge(admin_address, admin_sig).token

    user_challenge = auth.create_challenge(user_address)
    user_sig = sign_challenge(user_private, user_challenge)
    user_token = auth.verify_challenge(user_address, user_sig).token

    # Sign content
    content = "This is a structured contribution with evidence and reasoning."
    signed_at = datetime.now(timezone.utc).isoformat()
    message = build_contribution_message(
        agent_address=user_address,
        content=content,
        signed_at=signed_at,
        content_type="post",
    )
    signing_key = SigningKey(user_private, encoder=HexEncoder)
    signature = signing_key.sign(message).signature.hex()

    # Create post (should be queued)
    resp = client.post(
        "/posts",
        json={
            "content": content,
            "signature": signature,
            "signed_at": signed_at,
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    queue_id = data["queue_id"]

    # Queue should include item
    q_resp = client.get(
        "/admin/queue",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert q_resp.status_code == 200
    queue_data = q_resp.json()
    # Handle both list and dict with "items" key
    items = queue_data if isinstance(queue_data, list) else queue_data.get("items", [])
    assert any(item["id"] == queue_id for item in items)

    # Posts list should be empty before approval
    posts_resp = client.get("/posts")
    assert posts_resp.status_code == 200
    assert posts_resp.json() == []

    # Approve using new unified route
    approve_resp = client.post(
        f"/admin/queue/{queue_id}/approve",
        json={"reason": "meets quality bar"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # Posts list should include the approved post
    posts_resp = client.get("/posts")
    assert posts_resp.status_code == 200
    assert len(posts_resp.json()) == 1

    # Witness chain should record approval
    actions = [entry["action"] for entry in api_unified._moderation.witness.list_entries(content_id=str(queue_id))]
    assert "moderation_approved" in actions


@pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
def test_admin_queue_list_endpoint(api_client, monkeypatch):
    """Test GET /admin/queue returns pending items."""
    client, api_unified, db_path = api_client

    auth = api_unified._auth

    # Register admin
    admin_private, admin_public = generate_agent_keypair()
    admin_address = auth.register("admin-agent", admin_public, telos="moderate")
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", admin_address)

    admin_challenge = auth.create_challenge(admin_address)
    admin_sig = sign_challenge(admin_private, admin_challenge)
    admin_token = auth.verify_challenge(admin_address, admin_sig).token

    # Register user and create posts
    user_private, user_public = generate_agent_keypair()
    user_address = auth.register("user-agent", user_public, telos="contribute")
    user_challenge = auth.create_challenge(user_address)
    user_sig = sign_challenge(user_private, user_challenge)
    user_token = auth.verify_challenge(user_address, user_sig).token

    # Create 3 posts
    queue_ids = []
    for i in range(3):
        content = f"Structured research post number {i} with sufficient length and content."
        signed_at = datetime.now(timezone.utc).isoformat()
        message = build_contribution_message(
            agent_address=user_address,
            content=content,
            signed_at=signed_at,
            content_type="post",
        )
        signing_key = SigningKey(user_private, encoder=HexEncoder)
        signature = signing_key.sign(message).signature.hex()

        resp = client.post(
            "/posts",
            json={"content": content, "signature": signature, "signed_at": signed_at},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 201
        queue_ids.append(resp.json()["queue_id"])

    # Get queue
    q_resp = client.get("/admin/queue", headers={"Authorization": f"Bearer {admin_token}"})
    assert q_resp.status_code == 200
    queue_data = q_resp.json()
    items = queue_data if isinstance(queue_data, list) else queue_data.get("items", [])
    assert len(items) == 3

    # All should be in queue
    item_ids = [item["id"] for item in items]
    for qid in queue_ids:
        assert qid in item_ids
