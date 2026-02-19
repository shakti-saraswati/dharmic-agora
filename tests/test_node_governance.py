from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agora.node_governance import (
    STAGE_CANON,
    STAGE_PAPER_EXTERNAL,
    STAGE_PAPER_INTERNAL,
    STAGE_VENTURE_EXTERNAL,
    STAGE_VENTURE_PROPOSAL,
    evaluate_claim_for_stage,
)


NOW = datetime(2026, 2, 19, tzinfo=timezone.utc)


def _base_claim() -> dict:
    completed = (NOW - timedelta(days=16)).isoformat()
    return {
        "claim_id": "claim-rv-depth-001",
        "node_id": "anchor-03-ml-intelligence-engineering",
        "title": "Depth concentration hypothesis",
        "lane": "papers",
        "status": "witnessed",
        "proposal_hash": "a" * 32,
        "summary": "Cross-architecture RV contraction concentration test plan.",
        "cross_model_affirm_count": 3,
        "non_adjacent_witness_count": 2,
        "cross_node_refs": [
            {
                "node_id": "anchor-05-ecology-earth-systems",
                "witness_ref": "wit-eco-001",
            },
            {
                "node_id": "anchor-07-dharmic-jain-epistemics",
                "witness_ref": "wit-dharma-001",
            },
        ],
        "artifact_refs": ["artifacts/rv_measurement_v4.py"],
        "red_team_refs": ["redteam/angle-1.md", "redteam/angle-2.md"],
        "human_review_refs": ["reviews/human-review-1.md"],
        "citation_pack_refs": ["citations/rv-depth-pack.md"],
        "sublation_refs": ["sublations/sub-legacy-threshold.md"],
        "replaces_prior_frame": False,
        "capture_risk_assessment_refs": ["assessments/capture-risk.md"],
        "public_good_impact_refs": ["assessments/public-good-impact.md"],
        "threshold_completed_at": completed,
        "cooldown_until": (NOW - timedelta(days=1)).isoformat(),
        "quarantine_complete": True,
        "externalization_ready": True,
        "created_at": (NOW - timedelta(days=17)).isoformat(),
        "updated_at": completed,
    }


def test_paper_internal_draft_passes() -> None:
    claim = _base_claim()
    result = evaluate_claim_for_stage(claim, STAGE_PAPER_INTERNAL, now=NOW)
    assert result.passed is True
    assert result.errors == []


def test_paper_internal_draft_fails_without_red_team_memo() -> None:
    claim = _base_claim()
    claim["red_team_refs"] = []
    result = evaluate_claim_for_stage(claim, STAGE_PAPER_INTERNAL, now=NOW)
    assert result.passed is False
    assert any("red-team" in msg for msg in result.errors)


def test_paper_external_submission_requires_human_review() -> None:
    claim = _base_claim()
    claim["human_review_refs"] = []
    result = evaluate_claim_for_stage(claim, STAGE_PAPER_EXTERNAL, now=NOW)
    assert result.passed is False
    assert any("human review" in msg for msg in result.errors)


def test_canon_propagation_requires_cooldown_elapsed() -> None:
    claim = _base_claim()
    claim["threshold_completed_at"] = (NOW - timedelta(days=2)).isoformat()
    claim["cooldown_until"] = (NOW + timedelta(days=1)).isoformat()
    result = evaluate_claim_for_stage(claim, STAGE_CANON, now=NOW)
    assert result.passed is False
    assert any("cooldown" in msg for msg in result.errors)


def test_canon_propagation_requires_sublation_when_replacing_prior_frame() -> None:
    claim = _base_claim()
    claim["replaces_prior_frame"] = True
    claim["sublation_refs"] = []
    result = evaluate_claim_for_stage(claim, STAGE_CANON, now=NOW)
    assert result.passed is False
    assert any("sublation" in msg for msg in result.errors)


def test_canon_propagation_requires_explicit_non_adjacent_witnesses() -> None:
    claim = _base_claim()
    claim["cross_node_refs"] = [
        {
            "node_id": "anchor-05-ecology-earth-systems",
            "witness_ref": "wit-eco-001",
        }
    ]
    claim["non_adjacent_witness_count"] = 1
    result = evaluate_claim_for_stage(claim, STAGE_CANON, now=NOW)
    assert result.passed is False
    assert any("non-adjacent" in msg for msg in result.errors)


def test_non_adjacent_declared_count_cannot_exceed_explicit_witness_refs() -> None:
    claim = _base_claim()
    claim["cross_node_refs"] = [
        {
            "node_id": "anchor-05-ecology-earth-systems",
            "witness_ref": "wit-eco-001",
        }
    ]
    claim["non_adjacent_witness_count"] = 4
    result = evaluate_claim_for_stage(claim, STAGE_PAPER_INTERNAL, now=NOW)
    assert result.passed is False
    assert any("declared non_adjacent_witness_count exceeds explicit" in msg for msg in result.errors)


def test_venture_proposal_requires_two_red_team_memos() -> None:
    claim = _base_claim()
    claim["red_team_refs"] = ["redteam/angle-1.md"]
    result = evaluate_claim_for_stage(claim, STAGE_VENTURE_PROPOSAL, now=NOW)
    assert result.passed is False
    assert any("red-team memos" in msg for msg in result.errors)


def test_venture_external_release_requires_assessments_and_quarantine() -> None:
    claim = _base_claim()
    claim["capture_risk_assessment_refs"] = []
    claim["public_good_impact_refs"] = []
    claim["quarantine_complete"] = False
    claim["externalization_ready"] = False
    claim["cooldown_until"] = (NOW + timedelta(days=2)).isoformat()
    result = evaluate_claim_for_stage(claim, STAGE_VENTURE_EXTERNAL, now=NOW)
    assert result.passed is False
    assert any("capture-risk assessment" in msg for msg in result.errors)
    assert any("public-good impact assessment" in msg for msg in result.errors)
    assert any("quarantine" in msg for msg in result.errors)


def test_venture_external_release_passes_when_requirements_met() -> None:
    claim = _base_claim()
    claim["cooldown_until"] = (NOW - timedelta(days=1)).isoformat()
    result = evaluate_claim_for_stage(claim, STAGE_VENTURE_EXTERNAL, now=NOW)
    assert result.passed is True
    assert result.errors == []


def test_unknown_stage_fails() -> None:
    claim = _base_claim()
    result = evaluate_claim_for_stage(claim, "unknown-stage", now=NOW)
    assert result.passed is False
    assert "unknown stage" in result.errors[0]
