from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _fresh_client(tmp_path: Path, monkeypatch, shared_secret: str | None) -> TestClient:
    db_path = tmp_path / "federation_test.db"
    fed_dir = tmp_path / "federation_data"
    shadow_summary = tmp_path / "shadow_loop" / "run_summary.json"
    shadow_summary.parent.mkdir(parents=True, exist_ok=True)
    shadow_summary.write_text(
        json.dumps(
            {
                "timestamp": "2026-02-19T00:00:00+00:00",
                "status": "stable",
                "alert_count": 0,
                "high_alert_count": 0,
            }
        )
    )

    monkeypatch.setenv("SAB_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")
    monkeypatch.setenv("SAB_SHADOW_SUMMARY_PATH", str(shadow_summary))
    monkeypatch.setenv("SAB_DGC_SHARED_SECRET", "test-shared-secret")
    monkeypatch.setenv("SAB_FEDERATION_DATA_DIR", str(fed_dir))
    if shared_secret is None:
        monkeypatch.delenv("SAB_FEDERATION_SHARED_SECRET", raising=False)
    else:
        monkeypatch.setenv("SAB_FEDERATION_SHARED_SECRET", shared_secret)

    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]

    api_server = importlib.import_module("agora.api_server")
    return TestClient(api_server.app)


def _agent_payload() -> dict:
    return {
        "agent_id": "agent-alpha",
        "host": "127.0.0.1:9000",
        "capabilities": ["evaluate", "moderate"],
        "models": ["gpt-5", "claude-opus-4-6"],
        "status": "active",
    }


def test_federation_open_when_secret_not_set(tmp_path: Path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch, shared_secret=None)

    reg = client.post("/api/federation/register_agent", json=_agent_payload())
    assert reg.status_code == 200
    assert reg.json()["agent_id"] == "agent-alpha"

    health = client.get("/api/federation/health")
    assert health.status_code == 200
    assert health.json()["registered_agents"] == 1


def test_federation_rejects_missing_secret_when_configured(tmp_path: Path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch, shared_secret="fed-secret-123")

    reg = client.post("/api/federation/register_agent", json=_agent_payload())
    assert reg.status_code == 401
    assert "Invalid federation shared secret" in reg.json()["detail"]

    health = client.get("/api/federation/health")
    assert health.status_code == 401


def test_federation_accepts_valid_secret_header(tmp_path: Path, monkeypatch) -> None:
    secret = "fed-secret-123"
    client = _fresh_client(tmp_path, monkeypatch, shared_secret=secret)
    headers = {"X-SAB-Federation-Secret": secret}

    reg = client.post("/api/federation/register_agent", json=_agent_payload(), headers=headers)
    assert reg.status_code == 200

    list_resp = client.get("/api/federation/agents", headers=headers)
    assert list_resp.status_code == 200
    assert "agent-alpha" in list_resp.json()
