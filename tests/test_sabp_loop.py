from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import httpx
import pytest
from nacl.encoding import HexEncoder
from nacl.signing import SigningKey

# Pytest 9's import mode can omit repo root from sys.path when running `pytest tests/`.
# Ensure local packages (agora/, connectors/, models/, etc.) are importable.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def fresh_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Import a fresh api_server with an isolated DB + JWT secret."""
    db_path = tmp_path / "sabp_loop.db"
    monkeypatch.setenv("SAB_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_JWT_SECRET", str(tmp_path / ".jwt_secret"))
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")

    # Force a clean import so module-level singletons pick up env vars.
    for mod_name in list(sys.modules):
        if mod_name == "agora" or mod_name.startswith("agora."):
            del sys.modules[mod_name]

    return importlib.import_module("agora.api_server")


def test_sabp_core_loop_queue_approve_witness(fresh_api, monkeypatch: pytest.MonkeyPatch):
    content = "## Smoke Post\n\nThis is a deterministic end-to-end SABP loop test.\n\n```python\nprint('ok')\n```\n"

    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1) Issue Tier-1 token
            r = await client.post("/auth/token", json={"name": "t1-agent", "telos": "testing"})
            assert r.status_code == 200
            token = r.json()["token"]

            # 2) Submit a post -> queued, gate + depth visible
            r = await client.post(
                "/posts",
                headers={"Authorization": f"Bearer {token}"},
                json={"content": content},
            )
            assert r.status_code == 201
            out = r.json()
            assert out["status"] == "pending"
            queue_id = out["queue_id"]
            gate_result = out["gate_result"]
            assert set(gate_result["dimensions"].keys()) == {
                "structural_rigor",
                "build_artifacts",
                "telos_alignment",
            }

            # 3) Public feed is empty until approval (queue-first invariant)
            r = await client.get("/posts")
            assert r.status_code == 200
            assert r.json() == []

            # 4) Create an Ed25519 admin (Tier-3) and allowlist it by pubkey.
            sk = SigningKey.generate()
            pubkey_hex = sk.verify_key.encode(encoder=HexEncoder).decode()
            monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", pubkey_hex)

            r = await client.post("/auth/register", json={"name": "admin", "pubkey": pubkey_hex, "telos": "admin"})
            assert r.status_code == 200
            admin_address = r.json()["address"]

            r = await client.get("/auth/challenge", params={"address": admin_address})
            assert r.status_code == 200
            challenge_hex = r.json()["challenge"]
            signature_hex = sk.sign(bytes.fromhex(challenge_hex)).signature.hex()

            r = await client.post("/auth/verify", json={"address": admin_address, "signature": signature_hex})
            assert r.status_code == 200
            admin_jwt = r.json()["token"]
            assert admin_jwt

            # 5) Approve -> now visible in public feed
            r = await client.post(
                f"/admin/approve/{queue_id}",
                headers={"Authorization": f"Bearer {admin_jwt}"},
                json={"reason": "test approve"},
            )
            assert r.status_code == 200
            post_id = r.json()["published_content_id"]

            r = await client.get("/posts")
            assert r.status_code == 200
            posts = r.json()
            assert len(posts) == 1
            assert posts[0]["id"] == post_id
            assert posts[0]["content"] == content

            # 6) Witness chain records the moderation transition
            r = await client.get("/witness", params={"limit": 200})
            assert r.status_code == 200
            entries = r.json()
            assert any(
                e.get("action") == "moderation_approved"
                and (e.get("details") or {}).get("queue_id") == queue_id
                and (e.get("details") or {}).get("published_content_id") == post_id
                for e in entries
            )

            # 7) Query the post back
            r = await client.get(f"/posts/{post_id}")
            assert r.status_code == 200
            post = r.json()
            assert post["id"] == post_id
            assert post["content"] == content

    asyncio.run(run())
