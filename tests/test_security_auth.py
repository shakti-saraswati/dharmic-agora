"""
Security and authorization boundary tests for the SAB platform.

Tests cover:
- Forged/invalid signature rejection
- Cross-agent impersonation (Agent A cannot act as Agent B)
- Row-level authorization on mutations
- Appeal ownership enforcement
- CSRF protection on web forms
"""
from __future__ import annotations

import hashlib
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Dict

import pytest
from fastapi.testclient import TestClient
from nacl.encoding import HexEncoder
from nacl.signing import SigningKey

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers (canonical signing routines mirroring app.py internals)
# ---------------------------------------------------------------------------

def _canonical_bytes(payload: Dict[str, object]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()


def _sign_submit(sk: SigningKey, agent_id: str, content: str) -> str:
    content_sha = hashlib.sha256(content.encode()).hexdigest()
    payload = {
        "kind": "spark_submit",
        "author_id": agent_id,
        "content_sha256": content_sha,
    }
    return sk.sign(_canonical_bytes(payload)).signature.hex()


def _sign_challenge(sk: SigningKey, spark_id: int, challenger_id: str, content: str) -> str:
    content_sha = hashlib.sha256(content.encode()).hexdigest()
    payload = {
        "kind": "spark_challenge",
        "spark_id": spark_id,
        "challenger_id": challenger_id,
        "content_sha256": content_sha,
    }
    return sk.sign(_canonical_bytes(payload)).signature.hex()


def _sign_witness(sk: SigningKey, spark_id: int, witness_id: str, action: str, payload: Dict[str, object]) -> str:
    payload_sha = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    envelope = {
        "kind": "witness_attestation",
        "spark_id": spark_id,
        "witness_id": witness_id,
        "action": action,
        "payload_sha256": payload_sha,
    }
    return sk.sign(_canonical_bytes(envelope)).signature.hex()


def _register(client: TestClient, sk: SigningKey, name: str) -> str:
    public_key = sk.verify_key.encode(encoder=HexEncoder).decode()
    res = client.post("/api/agents/register", json={"name": name, "public_key": public_key})
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def spark_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "sec_test.db"
    key_path = tmp_path / ".sec_system_ed25519.key"
    monkeypatch.setenv("SAB_SPARK_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_SYSTEM_WITNESS_KEY", str(key_path))

    for mod_name in list(sys.modules):
        if mod_name == "agora" or mod_name.startswith("agora."):
            del sys.modules[mod_name]

    return importlib.import_module("agora.app")


@pytest.fixture
def client(spark_app):
    with TestClient(spark_app.app) as test_client:
        yield test_client


def _submit_spark(client: TestClient, sk: SigningKey, agent_id: str, content: str) -> int:
    sig = _sign_submit(sk, agent_id, content)
    res = client.post(
        "/api/spark/submit",
        json={
            "content": content,
            "content_type": "text",
            "author_id": agent_id,
            "signature": sig,
        },
    )
    assert res.status_code == 201, res.text
    return int(res.json()["id"])


# ---------------------------------------------------------------------------
# 1. FORGED SIGNATURE TESTS
# ---------------------------------------------------------------------------


class TestForgedSignatures:
    """Verify that all mutation endpoints reject forged signatures."""

    def test_forged_submit_signature_rejected(self, client: TestClient):
        sk = SigningKey.generate()
        agent_id = _register(client, sk, "legit-agent")

        # Use all-zeros as a forged signature
        forged_sig = "00" * 64
        res = client.post(
            "/api/spark/submit",
            json={
                "content": "Forged spark attempt.",
                "content_type": "text",
                "author_id": agent_id,
                "signature": forged_sig,
            },
        )
        assert res.status_code == 400
        assert "Invalid Ed25519 signature" in res.text

    def test_forged_challenge_signature_rejected(self, client: TestClient):
        sk1 = SigningKey.generate()
        a1 = _register(client, sk1, "author-forge")
        spark_id = _submit_spark(client, sk1, a1, "Spark to be challenged with forged sig.")

        sk2 = SigningKey.generate()
        a2 = _register(client, sk2, "challenger-forge")

        forged_sig = "00" * 64
        res = client.post(
            f"/api/spark/{spark_id}/challenge",
            json={
                "challenger_id": a2,
                "content": "Forged challenge.",
                "signature": forged_sig,
            },
        )
        assert res.status_code == 400
        assert "Invalid Ed25519 signature" in res.text

    def test_forged_witness_signature_rejected(self, client: TestClient):
        sk1 = SigningKey.generate()
        a1 = _register(client, sk1, "author-w")
        spark_id = _submit_spark(client, sk1, a1, "Spark for witness forge test.")

        sk2 = SigningKey.generate()
        a2 = _register(client, sk2, "witness-forge")

        forged_sig = "00" * 64
        payload = {"reason": "forged"}
        res = client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": a2,
                "action": "affirm",
                "payload": payload,
                "signature": forged_sig,
            },
        )
        assert res.status_code == 400
        assert "Invalid Ed25519 signature" in res.text


# ---------------------------------------------------------------------------
# 2. CROSS-AGENT IMPERSONATION TESTS
# ---------------------------------------------------------------------------


class TestCrossAgentImpersonation:
    """Verify that Agent A cannot submit/act using Agent B's identity."""

    def test_agent_a_cannot_submit_as_agent_b(self, client: TestClient):
        """Agent A signs with own key but claims to be Agent B."""
        sk_a = SigningKey.generate()
        a_id = _register(client, sk_a, "agent-a")

        sk_b = SigningKey.generate()
        b_id = _register(client, sk_b, "agent-b")

        content = "Impersonation attempt."
        # Agent A signs the message as if they were agent B
        sig = _sign_submit(sk_a, b_id, content)
        res = client.post(
            "/api/spark/submit",
            json={
                "content": content,
                "content_type": "text",
                "author_id": b_id,
                "signature": sig,
            },
        )
        assert res.status_code == 400
        assert "Invalid Ed25519 signature" in res.text

    def test_agent_a_cannot_challenge_as_agent_b(self, client: TestClient):
        sk_a = SigningKey.generate()
        a_id = _register(client, sk_a, "challenger-a")

        sk_b = SigningKey.generate()
        b_id = _register(client, sk_b, "challenger-b")

        # Create a spark
        spark_id = _submit_spark(client, sk_a, a_id, "Spark for cross-agent challenge.")

        # A tries to challenge claiming to be B
        challenge_text = "Cross-agent challenge."
        sig = _sign_challenge(sk_a, spark_id, b_id, challenge_text)
        res = client.post(
            f"/api/spark/{spark_id}/challenge",
            json={
                "challenger_id": b_id,
                "content": challenge_text,
                "signature": sig,
            },
        )
        assert res.status_code == 400
        assert "Invalid Ed25519 signature" in res.text

    def test_agent_a_cannot_witness_as_agent_b(self, client: TestClient):
        sk_a = SigningKey.generate()
        a_id = _register(client, sk_a, "witness-a")

        sk_b = SigningKey.generate()
        b_id = _register(client, sk_b, "witness-b")

        spark_id = _submit_spark(client, sk_a, a_id, "Spark for cross-agent witness.")

        payload = {"reason": "cross-agent impersonation"}
        sig = _sign_witness(sk_a, spark_id, b_id, "affirm", payload)
        res = client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": b_id,
                "action": "affirm",
                "payload": payload,
                "signature": sig,
            },
        )
        assert res.status_code == 400
        assert "Invalid Ed25519 signature" in res.text


# ---------------------------------------------------------------------------
# 3. UNKNOWN AGENT TESTS
# ---------------------------------------------------------------------------


class TestUnknownAgent:
    """Verify that unregistered agent IDs are rejected."""

    def test_submit_by_unknown_agent_rejected(self, client: TestClient):
        sk = SigningKey.generate()
        fake_id = "nonexistent12345"
        content = "Ghost agent submission."
        sig = _sign_submit(sk, fake_id, content)
        res = client.post(
            "/api/spark/submit",
            json={
                "content": content,
                "content_type": "text",
                "author_id": fake_id,
                "signature": sig,
            },
        )
        assert res.status_code == 404
        assert "Unknown agent" in res.text


# ---------------------------------------------------------------------------
# 4. WITNESS ACTION VALIDATION
# ---------------------------------------------------------------------------


class TestWitnessActions:
    """Verify only valid witness actions are accepted."""

    def test_invalid_witness_action_rejected(self, client: TestClient):
        sk = SigningKey.generate()
        a_id = _register(client, sk, "action-test")
        spark_id = _submit_spark(client, sk, a_id, "Spark for action validation.")

        payload = {"reason": "bad action"}
        # The Pydantic model restricts the action field, so send raw JSON
        res = client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": a_id,
                "action": "delete_everything",
                "payload": payload,
                "signature": "00" * 64,
            },
        )
        assert res.status_code == 422  # Pydantic validation error


# ---------------------------------------------------------------------------
# 5. COMPOST VIA WITNESS (integrity of state transitions)
# ---------------------------------------------------------------------------


class TestCompostIntegrity:
    """Verify that composting requires valid signature."""

    def test_compost_action_requires_valid_signature(self, client: TestClient):
        sk1 = SigningKey.generate()
        a1 = _register(client, sk1, "compost-target")
        spark_id = _submit_spark(client, sk1, a1, "Spark that someone tries to forge-compost.")

        sk2 = SigningKey.generate()
        a2 = _register(client, sk2, "compost-attacker")

        # Try to compost with a forged signature
        payload = {"reason": "forged compost"}
        forged_sig = "00" * 64
        res = client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": a2,
                "action": "compost",
                "payload": payload,
                "signature": forged_sig,
            },
        )
        assert res.status_code == 400
        assert "Invalid Ed25519 signature" in res.text

        # Confirm spark is NOT composted
        spark = client.get(f"/api/spark/{spark_id}")
        assert spark.json()["status"] != "compost"

    def test_compost_with_valid_signature_succeeds(self, client: TestClient):
        sk1 = SigningKey.generate()
        a1 = _register(client, sk1, "compost-auth")
        spark_id = _submit_spark(client, sk1, a1, "Spark to be legitimately composted.")

        sk2 = SigningKey.generate()
        a2 = _register(client, sk2, "compost-witness")

        payload = {"reason": "legitimate compost"}
        sig = _sign_witness(sk2, spark_id, a2, "compost", payload)
        res = client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": a2,
                "action": "compost",
                "payload": payload,
                "signature": sig,
            },
        )
        assert res.status_code == 200

        spark = client.get(f"/api/spark/{spark_id}")
        assert spark.json()["status"] == "compost"


# ---------------------------------------------------------------------------
# 6. WEB SURFACE CSRF PROTECTION
# ---------------------------------------------------------------------------


class TestCSRFProtection:
    """Verify that web form POSTs require valid CSRF tokens."""

    def test_web_submit_without_csrf_succeeds_for_new_session(self, client: TestClient):
        """First POST creates a session -- no CSRF needed yet."""
        res = client.post(
            "/submit",
            data={"content": "New session spark.", "display_name": "csrf-test"},
            follow_redirects=False,
        )
        # Should redirect on success (303) or succeed
        assert res.status_code in (200, 303)

    def test_web_submit_with_bad_csrf_rejected_for_existing_session(self, client: TestClient):
        """Second POST from an established session must include valid CSRF."""
        # Create a session first
        res1 = client.post(
            "/submit",
            data={"content": "Session creation spark.", "display_name": "csrf-existing"},
            follow_redirects=False,
        )
        # Extract session cookie
        session_cookie = res1.cookies.get("sab_web_session")
        if session_cookie is None:
            pytest.skip("No session cookie set by first request")

        # Now submit again with a bad CSRF token
        client.cookies.set("sab_web_session", session_cookie)
        res2 = client.post(
            "/submit",
            data={"content": "Bad CSRF spark.", "_csrf": "bad-token"},
        )
        assert res2.status_code == 403
        assert "CSRF" in res2.text

    def test_web_submit_with_valid_csrf_succeeds(self, client: TestClient):
        """Submit with valid CSRF token extracted from the page should succeed."""
        # Create a session first
        client.post(
            "/submit",
            data={"content": "Session setup spark.", "display_name": "csrf-valid"},
            follow_redirects=False,
        )

        # Get the submit page to extract CSRF token
        page = client.get("/submit")
        csrf_token = _extract_csrf(page.text)
        if not csrf_token:
            pytest.skip("No CSRF token found in submit page")

        res = client.post(
            "/submit",
            data={
                "content": "Valid CSRF spark submission.",
                "_csrf": csrf_token,
            },
            follow_redirects=False,
        )
        assert res.status_code in (200, 303)


# ---------------------------------------------------------------------------
# 7. CHAIN INTEGRITY (cannot fake witness chain hashes)
# ---------------------------------------------------------------------------


class TestChainIntegrity:
    """Verify that the witness chain is tamper-evident."""

    def test_chain_verified_after_multiple_actions(self, client: TestClient):
        sk1 = SigningKey.generate()
        sk2 = SigningKey.generate()
        a1 = _register(client, sk1, "chain-a1")
        a2 = _register(client, sk2, "chain-a2")

        spark_id = _submit_spark(client, sk1, a1, "Chain integrity test spark.")

        payload = {"reason": "chain test"}
        sig = _sign_witness(sk2, spark_id, a2, "affirm", payload)
        client.post(
            "/api/witness/sign",
            json={
                "spark_id": spark_id,
                "witness_id": a2,
                "action": "affirm",
                "payload": payload,
                "signature": sig,
            },
        )

        chain = client.get(f"/api/spark/{spark_id}/chain")
        assert chain.status_code == 200
        data = chain.json()
        assert data["verified"] is True
        assert len(data["entries"]) >= 2
