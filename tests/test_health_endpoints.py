from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def health_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "health.db"
    key_path = tmp_path / ".health_system_ed25519.key"
    monkeypatch.setenv("SAB_SPARK_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_SYSTEM_WITNESS_KEY", str(key_path))

    for mod_name in list(sys.modules):
        if mod_name == "agora" or mod_name.startswith("agora."):
            del sys.modules[mod_name]

    return importlib.import_module("agora.app")


@pytest.fixture
def client(health_app):
    with TestClient(health_app.app) as test_client:
        yield test_client


def test_health_legacy_endpoint(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert body["service"] == "sab-basin-app"


def test_healthz_endpoint(client: TestClient):
    res = client.get("/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "sab-basin-app"


def test_readyz_endpoint(client: TestClient):
    res = client.get("/readyz")
    assert res.status_code == 200
    body = res.json()
    assert body["ready"] is True
    assert body["status"] == "ready"
    assert body["checks"]["db"]["ok"] is True
    assert body["checks"]["system_key"]["ok"] is True


def test_web_cache_status_endpoint(client: TestClient):
    res = client.get("/api/web/cache/status")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "cache_entries" in body
    assert "session_entries" in body

    verbose = client.get("/api/web/cache/status?verbose=true")
    assert verbose.status_code == 200
    v_body = verbose.json()
    assert isinstance(v_body.get("cache_keys"), list)
