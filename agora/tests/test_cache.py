"""
Tests for the web cache layer in agora.app.

Verifies TTL expiry, invalidation on mutations, and instrumentation counters.
"""
import importlib
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder

    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False

pytestmark = pytest.mark.skipif(not NACL_AVAILABLE, reason="PyNaCl not available")


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    """Isolated app module with fresh DB and cache."""
    db_path = tmp_path / "spark.db"
    monkeypatch.setenv("SAB_SPARK_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_WEB_CACHE_TTL_SECONDS", "2")

    for mod_name in list(sys.modules):
        if mod_name.startswith("agora."):
            del sys.modules[mod_name]
    mod = importlib.import_module("agora.app")
    mod.init_db()
    return mod


def test_cache_hit_and_miss(app_module):
    """_cache_get returns None on miss, value on hit, and increments counters."""
    app_module._WEB_CACHE.clear()
    app_module._CACHE_STATS.update({"hits": 0, "misses": 0, "invalidations": 0})

    # Miss
    assert app_module._cache_get("nonexistent") is None
    assert app_module._CACHE_STATS["misses"] == 1

    # Set + Hit
    app_module._cache_set("key1", [{"id": 1}])
    result = app_module._cache_get("key1")
    assert result == [{"id": 1}]
    assert app_module._CACHE_STATS["hits"] == 1


def test_cache_ttl_expiry(app_module):
    """Entries expire after TTL and count as misses."""
    app_module._WEB_CACHE.clear()
    app_module._CACHE_STATS.update({"hits": 0, "misses": 0, "invalidations": 0})

    # Insert with a TTL of 2 seconds, then override expires_at to past
    app_module._cache_set("expire_me", "data")
    app_module._WEB_CACHE["expire_me"]["expires_at"] = time.time() - 1

    result = app_module._cache_get("expire_me")
    assert result is None
    assert app_module._CACHE_STATS["misses"] == 1
    assert "expire_me" not in app_module._WEB_CACHE


def test_invalidate_clears_all(app_module):
    """_invalidate_web_cache clears all entries and increments counter."""
    app_module._WEB_CACHE.clear()
    app_module._CACHE_STATS.update({"hits": 0, "misses": 0, "invalidations": 0})

    app_module._cache_set("a", 1)
    app_module._cache_set("b", 2)
    assert len(app_module._WEB_CACHE) == 2

    app_module._invalidate_web_cache()
    assert len(app_module._WEB_CACHE) == 0
    assert app_module._CACHE_STATS["invalidations"] == 1


def test_get_cache_stats_snapshot(app_module):
    """get_cache_stats returns current counters and metadata."""
    app_module._WEB_CACHE.clear()
    app_module._CACHE_STATS.update({"hits": 3, "misses": 7, "invalidations": 2})
    app_module._cache_set("x", "y")

    stats = app_module.get_cache_stats()
    assert stats["hits"] == 3
    assert stats["misses"] == 7
    assert stats["invalidations"] == 2
    assert stats["size"] == 1
    assert stats["ttl_seconds"] == 2


def test_submit_invalidates_cache(app_module):
    """Submitting a spark clears the web cache."""
    from fastapi.testclient import TestClient

    client = TestClient(app_module.app)

    # Warm the cache by loading the feed
    client.get("/")

    # Verify something is cached
    assert len(app_module._WEB_CACHE) > 0

    # Register an agent via the web surface
    resp = client.post("/register", data={"display_name": "cachetest"})
    assert resp.status_code in (200, 303)

    # Extract CSRF token from session for the submit POST
    csrf_token = ""
    for _, session_data in app_module._WEB_SESSIONS.items():
        csrf_token = session_data.get("csrf_token", "")
        if csrf_token:
            break

    # Submit a spark (this should invalidate cache)
    resp = client.post(
        "/submit",
        data={"content": "Cache invalidation test spark content here.", "display_name": "cachetest", "_csrf": csrf_token},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    # Cache should be empty after mutation
    assert len(app_module._WEB_CACHE) == 0
    assert app_module._CACHE_STATS["invalidations"] >= 1


def test_cache_stats_endpoint(app_module):
    """The /api/cache/stats endpoint returns valid JSON."""
    from fastapi.testclient import TestClient

    client = TestClient(app_module.app)
    resp = client.get("/api/cache/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "hits" in data
    assert "misses" in data
    assert "invalidations" in data
    assert "size" in data
    assert "ttl_seconds" in data
