"""
SAB Test Configuration — Shared fixtures for all tests using api_unified.
"""
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

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


@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    """Fresh unified API server with isolated database."""
    db_path = tmp_path / "sab_test.db"
    monkeypatch.setenv("SAB_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")

    # Force reimport to pick up new DB_PATH
    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]
    
    # Import the unified API
    api_unified = importlib.import_module("agora.api_unified")

    client = TestClient(api_unified.app)
    return client, api_unified, db_path


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """Alias for fresh_app for compatibility."""
    return fresh_app(tmp_path, monkeypatch)


def register_and_auth(api_module, monkeypatch=None, telos="research", is_admin=False):
    """Helper: register agent, get JWT token + signing key."""
    auth = api_module._auth
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


def sign_content(agent, content, content_type="post", post_id=None, parent_id=None):
    """Helper: sign content for submission."""
    if not NACL_AVAILABLE:
        return "dummy_sig", datetime.now(timezone.utc).isoformat()
    
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


# Export helpers
pytest.register_and_auth = register_and_auth
pytest.sign_content = sign_content
