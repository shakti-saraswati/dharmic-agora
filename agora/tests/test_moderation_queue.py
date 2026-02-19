#!/usr/bin/env python3
"""
SAB Moderation Queue Tests
"""

import importlib
import json
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
    monkeypatch.setenv("SAB_SHADOW_SUMMARY_PATH", str(shadow_summary))

    if "agora.api_server" in sys.modules:
        del sys.modules["agora.api_server"]
    api_server = importlib.import_module("agora.api_server")
    client = TestClient(api_server.app)
    return client, api_server, db_path


@pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")
def test_post_queued_then_approved(api_client, monkeypatch):
    client, api_server, db_path = api_client

    auth = api_server._auth

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
    items = q_resp.json().get("items", [])
    assert any(item["id"] == queue_id for item in items)

    # Posts list should be empty before approval
    posts_resp = client.get("/posts")
    assert posts_resp.status_code == 200
    assert posts_resp.json() == []

    # Approve
    approve_resp = client.post(
        f"/admin/approve/{queue_id}",
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
    actions = [entry["action"] for entry in api_server._moderation.witness.list_entries(content_id=str(queue_id))]
    assert "moderation_approved" in actions
