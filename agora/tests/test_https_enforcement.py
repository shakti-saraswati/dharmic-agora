from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _fresh_client(tmp_path: Path, monkeypatch, enforce_https: str) -> TestClient:
    db_path = tmp_path / "https_enforcement.db"
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
    monkeypatch.setenv("ENFORCE_HTTPS", enforce_https)

    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]

    api_server = importlib.import_module("agora.api_server")
    return TestClient(api_server.app)


def test_https_enforcement_blocks_http_when_enabled(tmp_path: Path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch, enforce_https="true")
    resp = client.get("/health", headers={"x-forwarded-proto": "http"})
    assert resp.status_code == 400
    assert resp.json() == {"error": "HTTPS required"}


def test_https_enforcement_allows_https_when_enabled(tmp_path: Path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch, enforce_https="true")
    resp = client.get("/health", headers={"x-forwarded-proto": "https"})
    assert resp.status_code == 200

