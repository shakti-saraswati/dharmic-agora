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
def web_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "web_surface.db"
    key_path = tmp_path / ".web_surface_system_ed25519.key"
    monkeypatch.setenv("SAB_SPARK_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_SYSTEM_WITNESS_KEY", str(key_path))

    for mod_name in list(sys.modules):
        if mod_name == "agora" or mod_name.startswith("agora."):
            del sys.modules[mod_name]

    return importlib.import_module("agora.app")


@pytest.fixture
def client(web_app):
    with TestClient(web_app.app) as test_client:
        yield test_client


def _submit_via_web(client: TestClient, content: str):
    response = client.post(
        "/submit",
        data={
            "display_name": "web-agent",
            "content": content,
            "content_type": "text",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    location = response.headers.get("location", "")
    assert location.startswith("/spark/")
    return location


def test_web_pages_render(client: TestClient):
    for path in ("/", "/submit", "/canon", "/compost", "/about", "/register"):
        res = client.get(path)
        assert res.status_code == 200, f"{path}: {res.text}"


def test_submit_flow_renders_dimension_profile(client: TestClient):
    location = _submit_via_web(client, "Sprint 2 web surface smoke test content.")
    spark_page = client.get(location)
    assert spark_page.status_code == 200
    assert "17 Gate Dimensions" in spark_page.text
    assert "R_V (experimental)" in spark_page.text


def test_challenge_flow_visible_on_spark_page(client: TestClient):
    location = _submit_via_web(client, "Spark to challenge.")
    spark_id = int(location.split("/")[2].split("?")[0])

    challenge = client.post(
        f"/spark/{spark_id}/challenge",
        data={"content": "Challenge argument from web form."},
        follow_redirects=False,
    )
    assert challenge.status_code == 303

    spark_page = client.get(f"/spark/{spark_id}")
    assert spark_page.status_code == 200
    assert "Challenge argument from web form." in spark_page.text


def test_compost_feed_shows_why_card(client: TestClient):
    _submit_via_web(client, "This content says kill yourself and should fail Ahimsa.")

    compost_page = client.get("/compost")
    assert compost_page.status_code == 200
    assert "WHY this is compost" in compost_page.text
    assert "Failed Ahimsa safety gate." in compost_page.text


def test_web_session_private_key_not_rendered(client: TestClient, web_app):
    register = client.post(
        "/register",
        data={"display_name": "privacy-agent"},
        follow_redirects=False,
    )
    assert register.status_code == 303

    session_token = client.cookies.get(web_app.WEB_SESSION_COOKIE)
    assert session_token
    session = web_app._WEB_SESSIONS.get(session_token)
    assert session is not None
    private_key_hex = str(session["private_key_hex"])

    page = client.get("/")
    assert page.status_code == 200
    assert private_key_hex not in page.text


def test_web_cache_invalidation_on_mutation_paths(client: TestClient, web_app):
    web_app._WEB_CACHE.clear()

    home = client.get("/")
    assert home.status_code == 200
    assert len(web_app._WEB_CACHE) > 0

    location = _submit_via_web(client, "Cache invalidation submit path")
    spark_id = int(location.split("/")[2].split("?")[0])
    assert len(web_app._WEB_CACHE) == 0

    canon = client.get("/canon")
    assert canon.status_code == 200
    assert len(web_app._WEB_CACHE) > 0

    challenge = client.post(
        f"/spark/{spark_id}/challenge",
        data={"content": "cache invalidation challenge"},
        follow_redirects=False,
    )
    assert challenge.status_code == 303
    assert len(web_app._WEB_CACHE) == 0

    client.get("/compost")
    assert len(web_app._WEB_CACHE) > 0

    witness = client.post(
        f"/spark/{spark_id}/witness",
        data={"action": "affirm", "note": "cache invalidation witness"},
        follow_redirects=False,
    )
    assert witness.status_code == 303
    assert len(web_app._WEB_CACHE) == 0
