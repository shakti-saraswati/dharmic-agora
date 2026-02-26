from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _prime_env(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "runtime_hardening.db"
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
    monkeypatch.setenv("ENFORCE_HTTPS", "false")


def _purge_agora_modules(preserve: set[str] | None = None) -> None:
    preserve = preserve or set()
    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth" and mod_name not in preserve:
            del sys.modules[mod_name]


def test_production_cors_rejects_http_origin(tmp_path: Path, monkeypatch) -> None:
    _prime_env(tmp_path, monkeypatch)
    monkeypatch.setenv("SAB_ENV", "production")
    monkeypatch.setenv("SAB_CORS_ORIGINS", "http://localhost:3000")

    _purge_agora_modules()
    with pytest.raises(RuntimeError, match="SAB_CORS_ORIGINS"):
        importlib.import_module("agora.api_server")


def test_production_cors_allows_https_origin(tmp_path: Path, monkeypatch) -> None:
    _prime_env(tmp_path, monkeypatch)
    monkeypatch.setenv("SAB_ENV", "production")
    monkeypatch.setenv("SAB_CORS_ORIGINS", "https://agora.example")

    _purge_agora_modules()
    api_server = importlib.import_module("agora.api_server")
    client = TestClient(api_server.app)
    resp = client.options(
        "/gates",
        headers={
            "Origin": "https://agora.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://agora.example"


def test_require_federation_fails_when_router_invalid(tmp_path: Path, monkeypatch) -> None:
    _prime_env(tmp_path, monkeypatch)
    monkeypatch.setenv("SAB_REQUIRE_FEDERATION", "true")

    fake = types.ModuleType("agora.federation")
    fake.federation_router = "invalid-router"
    sys.modules["agora.federation"] = fake

    _purge_agora_modules(preserve={"agora.federation"})
    try:
        with pytest.raises(RuntimeError, match="SAB_REQUIRE_FEDERATION=true"):
            importlib.import_module("agora.api_server")
    finally:
        sys.modules.pop("agora.federation", None)


def test_require_federation_false_tolerates_invalid_router(tmp_path: Path, monkeypatch) -> None:
    _prime_env(tmp_path, monkeypatch)
    monkeypatch.setenv("SAB_REQUIRE_FEDERATION", "false")

    fake = types.ModuleType("agora.federation")
    fake.federation_router = "invalid-router"
    sys.modules["agora.federation"] = fake

    _purge_agora_modules(preserve={"agora.federation"})
    try:
        api_server = importlib.import_module("agora.api_server")
        client = TestClient(api_server.app)
        assert client.get("/health").status_code == 200
    finally:
        sys.modules.pop("agora.federation", None)
