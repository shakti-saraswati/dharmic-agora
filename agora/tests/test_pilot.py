"""Tests for SAB 20-Agent Pilot Infrastructure."""
import pytest
from agora.pilot import PilotManager


@pytest.fixture
def pilot(tmp_path):
    return PilotManager(tmp_path / "pilot_test.db")


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
