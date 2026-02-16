from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def fresh_app(tmp_path, monkeypatch):
    db_path = tmp_path / "sab_convergence.db"
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
    monkeypatch.setenv("SAB_DGC_SHARED_SECRET", "test-shared-secret")

    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]

    api_server = importlib.import_module("agora.api_server")
    client = TestClient(api_server.app)
    return client


def test_dgc_ingest_and_landscape(fresh_app):
    client = fresh_app

    token_resp = client.post("/auth/token", json={"name": "agent-conv", "telos": "evaluation"})
    assert token_resp.status_code == 200
    token = token_resp.json()["token"]
    address = token_resp.json()["address"]
    headers = {"Authorization": f"Bearer {token}"}

    identity_resp = client.post(
        "/agents/identity",
        headers=headers,
        json={
            "base_model": "claude-opus-4-6",
            "alias": "AGNI",
            "timestamp": "2026-02-16T14:30:00Z",
            "perceived_role": "evaluator",
            "self_grade": 0.75,
            "context_hash": "ctx_0001",
            "task_affinity": ["evaluation", "research"],
        },
    )
    assert identity_resp.status_code == 200

    signal_resp = client.post(
        "/signals/dgc",
        headers={**headers, "X-SAB-DGC-Secret": "test-shared-secret"},
        json={
            "event_id": "evt-sync-1",
            "timestamp": "2026-02-16T14:31:00Z",
            "task_id": "task-eval-1",
            "task_type": "evaluation",
            "artifact_id": "artifact-eval-1",
            "gate_scores": {"satya": 0.91, "substance": 0.87},
            "collapse_dimensions": {"ritual_ack": 0.2},
            "mission_relevance": 0.89,
        },
    )
    assert signal_resp.status_code == 200
    assert signal_resp.json()["event_id"] == "evt-sync-1"
    assert signal_resp.json()["low_trust_flag"] is False

    trust_resp = client.get(f"/convergence/trust/{address}")
    assert trust_resp.status_code == 200
    assert trust_resp.json()["latest"]["signal_event_id"] == "evt-sync-1"

    landscape_resp = client.get("/convergence/landscape")
    assert landscape_resp.status_code == 200
    nodes = landscape_resp.json()["nodes"]
    assert any(node["agent_address"] == address for node in nodes)
