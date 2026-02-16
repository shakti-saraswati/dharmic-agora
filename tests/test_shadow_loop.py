from agora.security.anomaly_detection import detect_anomalies
from agora.security.compliance_profile import generate_profile
from agora.security.safety_case_report import generate_report
from scripts.orthogonal_safety_loop import run_loop


def test_shadow_security_modules_execute():
    profile = generate_profile()
    assert profile.timestamp
    assert profile.redteam_summary.get("status") in {"ok", "missing"}

    alerts = detect_anomalies()
    assert isinstance(alerts, list)


def test_safety_case_report_contains_snapshot():
    profile = generate_profile()
    report = generate_report(profile=profile)
    assert "Current Evidence Snapshot" in report


def test_shadow_loop_runner_writes_outputs(tmp_path):
    summary = run_loop(tmp_path)
    assert (tmp_path / "acp_profile.json").exists()
    assert (tmp_path / "anomaly_alerts.json").exists()
    assert (tmp_path / "safety_case_report.md").exists()
    assert (tmp_path / "run_summary.json").exists()
    assert summary["status"] in {"stable", "alerting"}
