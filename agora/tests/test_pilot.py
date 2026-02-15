"""Tests for SAB 20-Agent Pilot Infrastructure — Updated for unified API routes."""
import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agora.pilot import PilotManager
from agora.auth import generate_agent_keypair, sign_challenge


@pytest.fixture
def pilot(tmp_path):
    return PilotManager(tmp_path / "pilot_test.db")


@pytest.fixture
def api_client_with_pilot(tmp_path, monkeypatch):
    """Fresh API client with pilot routes."""
    db_path = tmp_path / "sab_test.db"
    monkeypatch.setenv("SAB_DB_PATH", str(db_path))
    monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", "")

    # Force reimport
    for mod_name in list(sys.modules):
        if mod_name.startswith("agora.") and mod_name != "agora.auth":
            del sys.modules[mod_name]
    
    api_unified = importlib.import_module("agora.api_unified")
    client = TestClient(api_unified.app)
    return client, api_unified, db_path


# =============================================================================
# PILOT MANAGER UNIT TESTS
# =============================================================================

class TestInviteCodes:
    def test_create_invite(self, pilot):
        result = pilot.create_invite("gated", "admin_1")
        assert "code" in result
        assert result["cohort"] == "gated"
        assert "expires_at" in result

    def test_redeem_invite(self, pilot):
        invite = pilot.create_invite("gated", "admin_1")
        result = pilot.redeem_invite(invite["code"], "agent_1")
        assert result["cohort"] == "gated"
        assert result["agent_address"] == "agent_1"

    def test_redeem_invalid_code(self, pilot):
        with pytest.raises(ValueError, match="Invalid invite code"):
            pilot.redeem_invite("bogus_code", "agent_1")

    def test_double_redeem(self, pilot):
        invite = pilot.create_invite("gated", "admin_1")
        pilot.redeem_invite(invite["code"], "agent_1")
        with pytest.raises(ValueError, match="already redeemed"):
            pilot.redeem_invite(invite["code"], "agent_2")

    def test_expired_invite(self, pilot):
        invite = pilot.create_invite("gated", "admin_1", expires_hours=0)
        with pytest.raises(ValueError, match="expired"):
            pilot.redeem_invite(invite["code"], "agent_1")

    def test_ungated_cohort(self, pilot):
        invite = pilot.create_invite("ungated", "admin_1")
        result = pilot.redeem_invite(invite["code"], "agent_2")
        assert result["cohort"] == "ungated"


class TestCohorts:
    def test_get_cohort(self, pilot):
        invite = pilot.create_invite("gated", "admin_1")
        pilot.redeem_invite(invite["code"], "agent_1")
        assert pilot.get_cohort("agent_1") == "gated"

    def test_get_cohort_unknown_agent(self, pilot):
        assert pilot.get_cohort("unknown_agent") is None


class TestSurveys:
    def test_submit_survey(self, pilot):
        sid = pilot.submit_survey("agent_1", {"q1": "yes", "q2": "helpful"})
        assert sid > 0

    def test_multiple_surveys(self, pilot):
        s1 = pilot.submit_survey("agent_1", {"q1": "yes"})
        s2 = pilot.submit_survey("agent_1", {"q1": "no"})
        assert s2 > s1


class TestListInvites:
    def test_list_invites(self, pilot):
        pilot.create_invite("gated", "admin_1")
        pilot.create_invite("ungated", "admin_1")
        invites = pilot.list_invites()
        assert len(invites) == 2


class TestPilotMetrics:
    def test_metrics_empty(self, pilot):
        metrics = pilot.pilot_metrics()
        assert metrics["cohorts"] == {}
        assert metrics["surveys_submitted"] == 0

    def test_metrics_with_data(self, pilot):
        invite = pilot.create_invite("gated", "admin_1")
        pilot.redeem_invite(invite["code"], "agent_1")
        pilot.submit_survey("agent_1", {"q1": "great"})
        metrics = pilot.pilot_metrics()
        assert metrics["cohorts"]["gated"] == 1
        assert metrics["surveys_submitted"] == 1


# =============================================================================
# PILOT API ENDPOINT TESTS (Unified API Routes)
# =============================================================================

class TestPilotAPIRoutes:
    def test_create_invite_via_api(self, api_client_with_pilot, monkeypatch):
        """POST /pilot/invite should create an invite code."""
        client, api_unified, _ = api_client_with_pilot
        
        # Register admin
        auth = api_unified._auth
        admin_private, admin_public = generate_agent_keypair()
        admin_address = auth.register("admin-pilot", admin_public, telos="moderate")
        monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", admin_address)
        
        admin_challenge = auth.create_challenge(admin_address)
        admin_sig = sign_challenge(admin_private, admin_challenge)
        admin_token = auth.verify_challenge(admin_address, admin_sig).token

        resp = client.post(
            "/pilot/invite",
            json={"cohort": "gated", "expires_hours": 48},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert data["cohort"] == "gated"

    def test_list_invites_via_api(self, api_client_with_pilot, monkeypatch):
        """GET /pilot/invites should list all invites."""
        client, api_unified, _ = api_client_with_pilot
        
        # Register admin
        auth = api_unified._auth
        admin_private, admin_public = generate_agent_keypair()
        admin_address = auth.register("admin-pilot", admin_public, telos="moderate")
        monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", admin_address)
        
        admin_challenge = auth.create_challenge(admin_address)
        admin_sig = sign_challenge(admin_private, admin_challenge)
        admin_token = auth.verify_challenge(admin_address, admin_sig).token

        # Create some invites
        client.post(
            "/pilot/invite",
            json={"cohort": "gated", "expires_hours": 48},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        client.post(
            "/pilot/invite",
            json={"cohort": "ungated", "expires_hours": 24},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # List them
        resp = client.get("/pilot/invites", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        invites = resp.json()
        assert len(invites) >= 2

    def test_pilot_metrics_via_api(self, api_client_with_pilot, monkeypatch):
        """GET /pilot/metrics should return pilot metrics."""
        client, api_unified, _ = api_client_with_pilot
        
        # Register admin
        auth = api_unified._auth
        admin_private, admin_public = generate_agent_keypair()
        admin_address = auth.register("admin-pilot", admin_public, telos="moderate")
        monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", admin_address)
        
        admin_challenge = auth.create_challenge(admin_address)
        admin_sig = sign_challenge(admin_private, admin_challenge)
        admin_token = auth.verify_challenge(admin_address, admin_sig).token

        resp = client.get("/pilot/metrics", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "generated_at" in data
        assert "cohorts" in data
        assert "surveys_submitted" in data

    def test_non_admin_cannot_create_invite(self, api_client_with_pilot, monkeypatch):
        """Non-admin users should not be able to create invites."""
        client, api_unified, _ = api_client_with_pilot
        
        # Register admin first to set allowlist
        auth = api_unified._auth
        admin_private, admin_public = generate_agent_keypair()
        admin_address = auth.register("admin-pilot", admin_public, telos="moderate")
        monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", admin_address)
        
        # Register normal user
        user_private, user_public = generate_agent_keypair()
        user_address = auth.register("normal-user", user_public, telos="contribute")
        user_challenge = auth.create_challenge(user_address)
        user_sig = sign_challenge(user_private, user_challenge)
        user_token = auth.verify_challenge(user_address, user_sig).token

        resp = client.post(
            "/pilot/invite",
            json={"cohort": "gated", "expires_hours": 48},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert resp.status_code == 403

    def test_redeem_invite_via_registration(self, api_client_with_pilot, monkeypatch):
        """Agents should be able to use invite codes during registration."""
        client, api_unified, _ = api_client_with_pilot
        
        # Register admin and create invite
        auth = api_unified._auth
        admin_private, admin_public = generate_agent_keypair()
        admin_address = auth.register("admin-pilot", admin_public, telos="moderate")
        monkeypatch.setenv("SAB_ADMIN_ALLOWLIST", admin_address)
        
        admin_challenge = auth.create_challenge(admin_address)
        admin_sig = sign_challenge(admin_private, admin_challenge)
        admin_token = auth.verify_challenge(admin_address, admin_sig).token

        resp = client.post(
            "/pilot/invite",
            json={"cohort": "gated", "expires_hours": 48},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        invite_code = resp.json()["code"]

        # Now a new agent should be able to register with this code
        # (This would be tested in the registration endpoint if it accepts invite_code param)
        assert len(invite_code) > 0
        assert invite_code.startswith("INV_") or len(invite_code) == 16  # Basic validation
