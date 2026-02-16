from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import asyncio
import httpx
import pytest

from connectors.sabp_client import SabpAsyncClient


@pytest.fixture
def fresh_api(tmp_path: Path, monkeypatch):
    """Import a fresh api_server with an isolated DB."""
    db_path = tmp_path / "sab_connectors.db"
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

    return importlib.import_module("agora.api_server")


def test_sabp_client_token_and_queue_only(fresh_api):
    async def run():
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            c = SabpAsyncClient("http://test", client=client)
            await c.issue_token("t1-agent", telos="testing")
            out = await c.submit_post("hello from a connector")
            assert "queue_id" in out

            # Queue-first invariant: nothing is visible until approved.
            posts = await c.list_posts()
            assert posts == []

    asyncio.run(run())


def test_sabp_client_convergence_flow(fresh_api):
    async def run():
        transport = httpx.ASGITransport(app=fresh_api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            c = SabpAsyncClient("http://test", client=client)
            token_data = await c.issue_token("diag-agent", telos="evaluation")
            address = token_data["address"]

            identity = await c.register_identity(
                {
                    "base_model": "claude-opus-4-6",
                    "alias": "AGNI",
                    "timestamp": "2026-02-16T14:30:00Z",
                    "perceived_role": "evaluator",
                    "self_grade": 0.7,
                    "context_hash": "ctx_convergence_001",
                    "task_affinity": ["evaluation", "research"],
                }
            )
            assert identity["status"] == "registered"

            signal = await c.ingest_dgc_signal(
                {
                    "event_id": "evt-client-1",
                    "timestamp": "2026-02-16T14:31:00Z",
                    "task_id": "task-1",
                    "task_type": "evaluation",
                    "artifact_id": "artifact-1",
                    "gate_scores": {"satya": 0.9, "substance": 0.85},
                    "collapse_dimensions": {"ritual_ack": 0.2},
                    "mission_relevance": 0.88,
                },
                dgc_shared_secret="test-shared-secret",
            )
            assert signal["event_id"] == "evt-client-1"

            trust = await c.trust_history(address)
            assert trust["latest"]["signal_event_id"] == "evt-client-1"

            landscape = await c.convergence_landscape()
            assert any(n["agent_address"] == address for n in landscape["nodes"])

    asyncio.run(run())
