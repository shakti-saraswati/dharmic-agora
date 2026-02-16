from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def fresh_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "sabp_convergence.db"
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
    monkeypatch.setenv("SAB_JWT_SECRET", str(tmp_path / ".jwt_secret"))
    monkeypatch.setenv("SAB_SHADOW_SUMMARY_PATH", str(shadow_summary))
    monkeypatch.setenv("SAB_DGC_SHARED_SECRET", "test-shared-secret")

    for mod_name in list(sys.modules):
        if mod_name == "agora" or mod_name.startswith("agora."):
            del sys.modules[mod_name]

    return importlib.import_module("agora.api_server")


def test_identity_signal_ingest_updates_trust_and_landscape(fresh_api):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_resp = await client.post("/auth/token", json={"name": "diag-agent", "telos": "evaluation"})
            assert token_resp.status_code == 200
            token = token_resp.json()["token"]
            address = token_resp.json()["address"]
            headers = {"Authorization": f"Bearer {token}"}

            identity_resp = await client.post(
                "/agents/identity",
                headers=headers,
                json={
                    "base_model": "claude-opus-4-6",
                    "alias": "AGNI",
                    "timestamp": "2026-02-16T14:30:00Z",
                    "perceived_role": "commander",
                    "self_grade": 0.7,
                    "context_hash": "ctx_abc12345",
                    "task_affinity": ["evaluation", "research"],
                },
            )
            assert identity_resp.status_code == 200
            assert identity_resp.json()["identity"]["alias"] == "AGNI"

            dgc_resp = await client.post(
                "/signals/dgc",
                headers={
                    **headers,
                    "X-SAB-DGC-Secret": "test-shared-secret",
                },
                json={
                    "event_id": "evt-001",
                    "timestamp": "2026-02-16T14:31:00Z",
                    "task_id": "task-1",
                    "task_type": "evaluation",
                    "artifact_id": "artifact-1",
                    "source_alias": "agni-dgc",
                    "gate_scores": {"satya": 0.95, "substance": 0.88, "coherence": 0.81},
                    "collapse_dimensions": {"ritual_ack": 0.12, "semantic_drift": 0.21},
                    "mission_relevance": 0.92,
                    "signature": "sig-v1",
                },
            )
            assert dgc_resp.status_code == 200
            trust_payload = dgc_resp.json()
            assert trust_payload["event_id"] == "evt-001"
            assert 0.0 <= trust_payload["trust_score"] <= 1.0
            assert trust_payload["low_trust_flag"] is False

            history_resp = await client.get(f"/convergence/trust/{address}", headers=headers)
            assert history_resp.status_code == 200
            latest = history_resp.json()["latest"]
            assert latest["signal_event_id"] == "evt-001"
            assert latest["task_type"] == "evaluation"
            assert latest["trust_score"] == trust_payload["trust_score"]

            landscape_resp = await client.get("/convergence/landscape")
            assert landscape_resp.status_code == 200
            nodes = landscape_resp.json()["nodes"]
            assert any(n["agent_address"] == address for n in nodes)

    asyncio.run(run())


def test_low_trust_signal_surfaces_diagnostic_causes(fresh_api):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_resp = await client.post("/auth/token", json={"name": "diag-agent-2", "telos": "research"})
            assert token_resp.status_code == 200
            token = token_resp.json()["token"]
            address = token_resp.json()["address"]
            headers = {"Authorization": f"Bearer {token}"}

            identity_resp = await client.post(
                "/agents/identity",
                headers=headers,
                json={
                    "base_model": "gpt-codex-5-3",
                    "alias": "DHARMIC_CLAWD",
                    "timestamp": "2026-02-16T15:00:00Z",
                    "perceived_role": "commander",
                    "self_grade": 0.95,
                    "context_hash": "ctx_lowtrust_001",
                    "task_affinity": ["evaluation", "research"],
                },
            )
            assert identity_resp.status_code == 200

            dgc_resp = await client.post(
                "/signals/dgc",
                headers={
                    **headers,
                    "X-SAB-DGC-Secret": "test-shared-secret",
                },
                json={
                    "event_id": "evt-low-001",
                    "timestamp": "2026-02-16T15:01:00Z",
                    "task_id": "task-ops-1",
                    "task_type": "ops_automation",
                    "artifact_id": "artifact-low-1",
                    "source_alias": "agni-dgc",
                    "gate_scores": {"satya": 0.2, "substance": 0.18, "coherence": 0.25},
                    "collapse_dimensions": {"ritual_ack": 0.92, "looped_ack": 0.84},
                    "mission_relevance": 0.2,
                    "signature": "sig-low-v1",
                },
            )
            assert dgc_resp.status_code == 200
            payload = dgc_resp.json()
            assert payload["low_trust_flag"] is True
            assert "satya" in payload["weak_gates"]
            assert "context_quality_gap" in payload["likely_causes"]
            assert "task_affinity_mismatch" in payload["likely_causes"]

            history = await client.get(f"/convergence/trust/{address}", headers=headers)
            assert history.status_code == 200
            latest = history.json()["latest"]
            assert latest["low_trust_flag"] is True
            assert latest["diagnostic"]["suggested_action"] == "reroute_to_affinity_or_improve_context"

    asyncio.run(run())
