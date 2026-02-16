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
            assert trust_payload["schema_version"] == "dgc.v1"
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


def test_dgc_contract_validation_and_event_id_conflict(fresh_api):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_resp = await client.post("/auth/token", json={"name": "diag-agent-3", "telos": "research"})
            assert token_resp.status_code == 200
            token = token_resp.json()["token"]
            headers = {"Authorization": f"Bearer {token}", "X-SAB-DGC-Secret": "test-shared-secret"}

            # Contract guard: gate scores must be in [0,1].
            bad_score = await client.post(
                "/signals/dgc",
                headers=headers,
                json={
                    "event_id": "evt-contract-bad-score",
                    "timestamp": "2026-02-16T16:01:00Z",
                    "task_type": "evaluation",
                    "gate_scores": {"satya": 1.2},
                    "collapse_dimensions": {"ritual_ack": 0.2},
                },
            )
            assert bad_score.status_code == 422

            payload = {
                "event_id": "evt-contract-replay",
                "timestamp": "2026-02-16T16:02:00Z",
                "task_id": "task-contract-1",
                "task_type": "evaluation",
                "artifact_id": "artifact-contract-1",
                "gate_scores": {"satya": 0.8, "substance": 0.75},
                "collapse_dimensions": {"ritual_ack": 0.2},
                "mission_relevance": 0.82,
            }

            first = await client.post("/signals/dgc", headers=headers, json=payload)
            assert first.status_code == 200
            assert first.json()["idempotent_replay"] is False
            first_trust = first.json()["trust_score"]

            second = await client.post("/signals/dgc", headers=headers, json=payload)
            assert second.status_code == 200
            assert second.json()["idempotent_replay"] is True
            assert second.json()["trust_score"] == first_trust

            # Same event_id with changed payload must fail conflict check.
            conflict = await client.post(
                "/signals/dgc",
                headers=headers,
                json={**payload, "mission_relevance": 0.2},
            )
            assert conflict.status_code == 409
            assert "event_id_conflict_payload_mismatch" in conflict.text

    asyncio.run(run())


def test_dgc_81_dimension_payload_and_cross_agent_conflict(fresh_api):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Agent A
            token_a = await client.post("/auth/token", json={"name": "agent-a", "telos": "evaluation"})
            assert token_a.status_code == 200
            headers_a = {
                "Authorization": f"Bearer {token_a.json()['token']}",
                "X-SAB-DGC-Secret": "test-shared-secret",
            }

            # Agent B
            token_b = await client.post("/auth/token", json={"name": "agent-b", "telos": "evaluation"})
            assert token_b.status_code == 200
            headers_b = {
                "Authorization": f"Bearer {token_b.json()['token']}",
                "X-SAB-DGC-Secret": "test-shared-secret",
            }

            collapse_81 = {f"dim_{i:02d}": (0.9 if i % 4 == 0 else 0.2) for i in range(1, 82)}
            payload = {
                "event_id": "evt-81dims-1",
                "schema_version": "dgc.v1",
                "timestamp": "2026-02-16T16:20:00Z",
                "task_id": "task-81",
                "task_type": "evaluation",
                "artifact_id": "artifact-81",
                "gate_scores": {"satya": 0.88, "substance": 0.84, "coherence": 0.8},
                "collapse_dimensions": collapse_81,
                "mission_relevance": 0.86,
            }

            ok = await client.post("/signals/dgc", headers=headers_a, json=payload)
            assert ok.status_code == 200
            body = ok.json()
            assert body["event_id"] == "evt-81dims-1"
            assert isinstance(body["trust_score"], float)

            history = await client.get(f"/convergence/trust/{token_a.json()['address']}", headers=headers_a)
            assert history.status_code == 200
            latest = history.json()["latest"]
            assert "liturgical_collapse_risk" in latest["likely_causes"]
            assert len(latest["high_collapse"]) >= 10

            # Cross-agent replay of same event_id must fail.
            conflict = await client.post("/signals/dgc", headers=headers_b, json=payload)
            assert conflict.status_code == 409
            assert "event_id_conflict_agent_mismatch" in conflict.text

    asyncio.run(run())


def test_dgc_audit_actions_match_success_replay_reject_paths(fresh_api):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_resp = await client.post("/auth/token", json={"name": "diag-audit", "telos": "evaluation"})
            assert token_resp.status_code == 200
            headers = {
                "Authorization": f"Bearer {token_resp.json()['token']}",
                "X-SAB-DGC-Secret": "test-shared-secret",
            }
            base_payload = {
                "event_id": "evt-audit-paths-1",
                "schema_version": "dgc.v1",
                "timestamp": "2026-02-16T16:30:00Z",
                "task_id": "task-audit-1",
                "task_type": "evaluation",
                "artifact_id": "artifact-audit-1",
                "gate_scores": {"satya": 0.8, "substance": 0.79},
                "collapse_dimensions": {"ritual_ack": 0.2},
                "mission_relevance": 0.8,
            }

            first = await client.post("/signals/dgc", headers=headers, json=base_payload)
            assert first.status_code == 200
            assert first.json()["idempotent_replay"] is False

            replay = await client.post("/signals/dgc", headers=headers, json=base_payload)
            assert replay.status_code == 200
            assert replay.json()["idempotent_replay"] is True

            conflict = await client.post(
                "/signals/dgc",
                headers=headers,
                json={**base_payload, "mission_relevance": 0.2},
            )
            assert conflict.status_code == 409

            ingested = await client.get("/audit", params={"action": "dgc_signal_ingested"})
            assert ingested.status_code == 200
            assert len(ingested.json()) == 1

            replayed = await client.get("/audit", params={"action": "dgc_signal_replayed"})
            assert replayed.status_code == 200
            assert len(replayed.json()) == 1

            rejected = await client.get("/audit", params={"action": "dgc_signal_rejected"})
            assert rejected.status_code == 200
            assert len(rejected.json()) == 1

    asyncio.run(run())


def test_concurrent_same_event_ingest_is_idempotent(fresh_api):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_resp = await client.post("/auth/token", json={"name": "diag-race", "telos": "evaluation"})
            assert token_resp.status_code == 200
            headers = {
                "Authorization": f"Bearer {token_resp.json()['token']}",
                "X-SAB-DGC-Secret": "test-shared-secret",
            }
            payload = {
                "event_id": "evt-race-1",
                "schema_version": "dgc.v1",
                "timestamp": "2026-02-16T16:40:00Z",
                "task_id": "task-race-1",
                "task_type": "evaluation",
                "artifact_id": "artifact-race-1",
                "gate_scores": {"satya": 0.86, "substance": 0.82},
                "collapse_dimensions": {"ritual_ack": 0.2},
                "mission_relevance": 0.84,
            }

            async def submit_once():
                return await client.post("/signals/dgc", headers=headers, json=payload)

            results = await asyncio.gather(*[submit_once() for _ in range(8)])
            assert all(r.status_code == 200 for r in results)
            bodies = [r.json() for r in results]
            assert any(b["idempotent_replay"] is False for b in bodies)
            assert any(b["idempotent_replay"] is True for b in bodies)

            history = await client.get(f"/convergence/trust/{token_resp.json()['address']}", headers=headers)
            assert history.status_code == 200
            assert len(history.json()["history"]) == 1
            assert history.json()["latest"]["signal_event_id"] == "evt-race-1"

    asyncio.run(run())


def test_dgc_secret_must_be_configured(fresh_api, monkeypatch: pytest.MonkeyPatch):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_resp = await client.post("/auth/token", json={"name": "diag-secret", "telos": "evaluation"})
            assert token_resp.status_code == 200
            headers = {
                "Authorization": f"Bearer {token_resp.json()['token']}",
                "X-SAB-DGC-Secret": "any-secret",
            }

            monkeypatch.delenv("SAB_DGC_SHARED_SECRET", raising=False)
            monkeypatch.delenv("SAB_ALLOW_DEV_DGC_SECRET", raising=False)

            resp = await client.post(
                "/signals/dgc",
                headers=headers,
                json={
                    "event_id": "evt-no-secret-1",
                    "schema_version": "dgc.v1",
                    "timestamp": "2026-02-16T16:50:00Z",
                    "task_type": "evaluation",
                    "gate_scores": {"satya": 0.8},
                    "collapse_dimensions": {"ritual_ack": 0.2},
                },
            )
            assert resp.status_code == 503
            assert "not configured" in resp.text

    asyncio.run(run())


def test_dev_dgc_secret_fallback_only_when_explicitly_enabled(
    fresh_api,
    monkeypatch: pytest.MonkeyPatch,
):
    async def run() -> None:
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_resp = await client.post("/auth/token", json={"name": "diag-secret-dev", "telos": "evaluation"})
            assert token_resp.status_code == 200

            monkeypatch.delenv("SAB_DGC_SHARED_SECRET", raising=False)
            monkeypatch.setenv("SAB_ALLOW_DEV_DGC_SECRET", "1")

            resp = await client.post(
                "/signals/dgc",
                headers={
                    "Authorization": f"Bearer {token_resp.json()['token']}",
                    "X-SAB-DGC-Secret": "sab_dev_secret",
                },
                json={
                    "event_id": "evt-dev-secret-1",
                    "schema_version": "dgc.v1",
                    "timestamp": "2026-02-16T16:51:00Z",
                    "task_type": "evaluation",
                    "gate_scores": {"satya": 0.81},
                    "collapse_dimensions": {"ritual_ack": 0.2},
                },
            )
            assert resp.status_code == 200
            assert resp.json()["event_id"] == "evt-dev-secret-1"

    asyncio.run(run())
