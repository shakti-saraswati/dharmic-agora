from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agora.claim_promotion import run_promotion_enforcement


NOW = datetime(2026, 2, 19, tzinfo=timezone.utc)


def _write_claim(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_claim(stage: str) -> dict:
    return {
        "claim_id": "claim-test-001",
        "node_id": "anchor-03-ml-intelligence-engineering",
        "title": "Depth concentration hypothesis",
        "lane": "papers",
        "status": "witnessed",
        "proposal_hash": "a" * 32,
        "requested_stage": stage,
        "cross_model_affirm_count": 3,
        "non_adjacent_witness_count": 2,
        "cross_node_refs": [
            {"node_id": "anchor-05-ecology-earth-systems", "witness_ref": "wit-eco-1"},
            {"node_id": "anchor-07-dharmic-jain-epistemics", "witness_ref": "wit-dharma-1"},
        ],
        "artifact_refs": ["artifacts/rv_measurement_v4.py"],
        "red_team_refs": ["redteam/angle-1.md", "redteam/angle-2.md"],
        "human_review_refs": ["reviews/human-1.md"],
        "citation_pack_refs": ["citations/canon-pack.md"],
        "sublation_refs": ["sublations/sub-1.md"],
        "capture_risk_assessment_refs": ["assessments/capture.md"],
        "public_good_impact_refs": ["assessments/public-good.md"],
        "threshold_completed_at": (NOW - timedelta(days=16)).isoformat(),
        "cooldown_until": (NOW - timedelta(days=1)).isoformat(),
        "quarantine_complete": True,
        "externalization_ready": True,
        "created_at": (NOW - timedelta(days=17)).isoformat(),
        "updated_at": (NOW - timedelta(days=16)).isoformat(),
    }


def test_no_claim_files_passes_by_default(tmp_path: Path) -> None:
    nodes_root = tmp_path / "nodes"
    report = run_promotion_enforcement(nodes_root=nodes_root, now=NOW)
    assert report.passed is True
    assert report.files_scanned == 0
    assert report.stage_evaluations == 0


def test_fails_on_no_claims_when_enabled(tmp_path: Path) -> None:
    nodes_root = tmp_path / "nodes"
    report = run_promotion_enforcement(nodes_root=nodes_root, fail_on_no_claims=True, now=NOW)
    assert report.passed is False
    assert any("no claim packets found" in f.get("error", "") for f in report.failures)


def test_requested_stage_passes_when_thresholds_met(tmp_path: Path) -> None:
    claim = _base_claim("canon_propagation")
    _write_claim(
        tmp_path / "nodes/anchors/anchor-03-ml-intelligence-engineering/claims/claim-1.json",
        claim,
    )
    report = run_promotion_enforcement(nodes_root=tmp_path / "nodes", now=NOW)
    assert report.passed is True
    assert report.claims_with_stage_requests == 1
    assert report.stage_evaluations == 1
    assert report.failures == []


def test_requested_stage_fails_when_thresholds_not_met(tmp_path: Path) -> None:
    claim = _base_claim("canon_propagation")
    claim["citation_pack_refs"] = []
    _write_claim(
        tmp_path / "nodes/anchors/anchor-03-ml-intelligence-engineering/claims/claim-2.json",
        claim,
    )
    report = run_promotion_enforcement(nodes_root=tmp_path / "nodes", now=NOW)
    assert report.passed is False
    assert any("citation pack" in " ".join(f.get("errors", [])) for f in report.failures)


def test_require_stage_fails_claim_without_requested_stage(tmp_path: Path) -> None:
    claim = _base_claim("paper_internal_draft")
    claim.pop("requested_stage", None)
    _write_claim(
        tmp_path / "nodes/anchors/anchor-03-ml-intelligence-engineering/claims/claim-3.json",
        claim,
    )
    report = run_promotion_enforcement(nodes_root=tmp_path / "nodes", require_stage=True, now=NOW)
    assert report.passed is False
    assert any("missing requested_stage" in f.get("error", "") for f in report.failures)

