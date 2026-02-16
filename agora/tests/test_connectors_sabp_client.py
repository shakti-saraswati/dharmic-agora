from __future__ import annotations

import importlib
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
    monkeypatch.setenv("SAB_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")

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
