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


def _get_csrf_token(web_app) -> str:
    """Extract a CSRF token from the first active web session."""
    sessions = getattr(web_app, "_WEB_SESSIONS", {})
    for _token, session_data in sessions.items():
        csrf = session_data.get("csrf_token", "")
        if csrf:
            return csrf
    return ""


def _submit_via_web(client: TestClient, content: str, web_app=None):
    form_data = {
        "display_name": "web-agent",
        "content": content,
        "content_type": "text",
    }
    if web_app is not None:
        csrf = _get_csrf_token(web_app)
        if csrf:
            form_data["_csrf"] = csrf
    response = client.post(
        "/submit",
        data=form_data,
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
    assert "R_V" in spark_page.text
    assert "EXPERIMENTAL" in spark_page.text


def test_challenge_flow_visible_on_spark_page(client: TestClient, web_app):
    location = _submit_via_web(client, "Spark to challenge.", web_app=web_app)
    spark_id = int(location.split("/")[2].split("?")[0])

    form_data = {"content": "Challenge argument from web form."}
    csrf = _get_csrf_token(web_app)
    if csrf:
        form_data["_csrf"] = csrf
    challenge = client.post(
        f"/spark/{spark_id}/challenge",
        data=form_data,
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
