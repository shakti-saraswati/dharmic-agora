#!/usr/bin/env python3
"""
Claim promotion governance enforcement for SAB node generative units.

This module turns node governance docs into executable checks:
- nodes/cross_node/thresholds.yaml
- nodes/cross_node/non_adjacent_pairs.yaml
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS_PATH = REPO_ROOT / "nodes" / "cross_node" / "thresholds.yaml"
NON_ADJ_PATH = REPO_ROOT / "nodes" / "cross_node" / "non_adjacent_pairs.yaml"

STAGE_PAPER_INTERNAL = "paper_internal_draft"
STAGE_PAPER_EXTERNAL = "paper_external_submission"
STAGE_CANON = "canon_propagation"
STAGE_VENTURE_PROPOSAL = "venture_proposal"
STAGE_VENTURE_EXTERNAL = "venture_external_release"

VALID_STAGES: Set[str] = {
    STAGE_PAPER_INTERNAL,
    STAGE_PAPER_EXTERNAL,
    STAGE_CANON,
    STAGE_VENTURE_PROPOSAL,
    STAGE_VENTURE_EXTERNAL,
}


@dataclass
class StageEvaluation:
    stage: str
    passed: bool
    errors: List[str]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return raw


def load_thresholds(path: Path = THRESHOLDS_PATH) -> Dict[str, Any]:
    """Load machine-readable governance thresholds."""
    return _load_yaml(path)


def load_non_adjacent_pairs(path: Path = NON_ADJ_PATH) -> Dict[str, Set[str]]:
    """Load non-adjacent witness map keyed by node id."""
    raw = _load_yaml(path).get("pairs", {})
    out: Dict[str, Set[str]] = {}
    if isinstance(raw, dict):
        for node_id, cfg in raw.items():
            if not isinstance(cfg, dict):
                continue
            values = cfg.get("non_adjacent", [])
            if isinstance(values, list):
                out[str(node_id)] = {str(v) for v in values}
    return out


def _count_list(packet: Mapping[str, Any], key: str) -> int:
    value = packet.get(key, [])
    if not isinstance(value, list):
        return 0
    return len(value)


def _count_explicit_non_adjacent_witnesses(
    claim: Mapping[str, Any],
    pairs_map: Mapping[str, Set[str]],
) -> int:
    claim_node = str(claim.get("node_id", ""))
    allowed = pairs_map.get(claim_node, set())
    refs = claim.get("cross_node_refs", [])
    if not isinstance(refs, list):
        return 0

    seen_nodes: Set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        witness_node = str(ref.get("node_id", ""))
        witness_ref = str(ref.get("witness_ref", "")).strip()
        if witness_node in allowed and witness_ref:
            seen_nodes.add(witness_node)
    return len(seen_nodes)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_iso(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts.strip():
        return None
    normalized = ts.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _has_cooldown_elapsed(
    claim: Mapping[str, Any],
    min_days: int,
    now: datetime,
) -> bool:
    cooldown_until = _parse_iso(claim.get("cooldown_until"))
    if cooldown_until is not None:
        return now >= cooldown_until

    completed = _parse_iso(claim.get("threshold_completed_at")) or _parse_iso(claim.get("updated_at"))
    if completed is None:
        return False
    return now >= (completed + timedelta(days=min_days))


def _common_metrics(claim: Mapping[str, Any], pairs_map: Mapping[str, Set[str]]) -> Dict[str, Any]:
    explicit_non_adj = _count_explicit_non_adjacent_witnesses(claim, pairs_map)
    declared_non_adj = _to_int(claim.get("non_adjacent_witness_count", 0))
    return {
        "claim_id": str(claim.get("claim_id", "")),
        "node_id": str(claim.get("node_id", "")),
        "lane": str(claim.get("lane", "")),
        "status": str(claim.get("status", "")),
        "cross_model_affirm_count": _to_int(claim.get("cross_model_affirm_count", 0)),
        "non_adjacent_witness_count_declared": declared_non_adj,
        "non_adjacent_witness_count_explicit": explicit_non_adj,
        "artifact_count": _count_list(claim, "artifact_refs"),
        "red_team_memo_count": _count_list(claim, "red_team_refs"),
        "human_review_count": _count_list(claim, "human_review_refs"),
        "citation_pack_count": _count_list(claim, "citation_pack_refs"),
        "sublation_ref_count": _count_list(claim, "sublation_refs"),
        "capture_risk_assessment_count": _count_list(claim, "capture_risk_assessment_refs"),
        "public_good_impact_assessment_count": _count_list(claim, "public_good_impact_refs"),
        "externalization_ready": bool(claim.get("externalization_ready", False)),
        "quarantine_complete": bool(claim.get("quarantine_complete", False)),
    }


def _validate_non_adjacent_integrity(metrics: Mapping[str, Any], errors: List[str]) -> None:
    declared = _to_int(metrics.get("non_adjacent_witness_count_declared", 0))
    explicit = _to_int(metrics.get("non_adjacent_witness_count_explicit", 0))
    if declared > explicit:
        errors.append(
            "declared non_adjacent_witness_count exceeds explicit cross_node_refs-backed witnesses"
        )


def _check_paper_internal(
    claim: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    metrics: Mapping[str, Any],
    errors: List[str],
) -> None:
    t = thresholds.get("paper", {}).get("internal_draft_trigger", {})
    if _to_int(metrics.get("cross_model_affirm_count")) < _to_int(t.get("cross_model_affirm_min", 0)):
        errors.append("insufficient cross-model affirm witnesses for internal paper draft")
    if _to_int(metrics.get("non_adjacent_witness_count_explicit")) < _to_int(
        t.get("non_adjacent_witness_min", 0)
    ):
        errors.append("insufficient explicit non-adjacent witness records for internal paper draft")
    if _to_int(metrics.get("artifact_count")) < _to_int(t.get("reproducible_artifact_min", 0)):
        errors.append("missing reproducible artifact references for internal paper draft")
    if _to_int(metrics.get("red_team_memo_count")) < _to_int(t.get("red_team_memo_min", 0)):
        errors.append("missing required red-team memo references for internal paper draft")


def _check_paper_external(
    claim: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    metrics: Mapping[str, Any],
    errors: List[str],
) -> None:
    t = thresholds.get("paper", {}).get("external_submission_trigger", {})
    if bool(t.get("require_internal_draft_trigger", True)):
        _check_paper_internal(claim, thresholds, metrics, errors)
    if _to_int(metrics.get("human_review_count")) < _to_int(t.get("human_review_min", 0)):
        errors.append("missing required human review reference(s) for external paper submission")


def _check_canon(
    claim: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    metrics: Mapping[str, Any],
    errors: List[str],
    now: datetime,
) -> None:
    t = thresholds.get("canon", {}).get("propagation_trigger", {})
    if _to_int(metrics.get("non_adjacent_witness_count_explicit")) < _to_int(
        t.get("non_adjacent_witness_min", 0)
    ):
        errors.append("insufficient explicit non-adjacent witnesses for canon propagation")
    if _to_int(metrics.get("artifact_count")) < _to_int(t.get("reproducible_artifact_min", 0)):
        errors.append("missing reproducible artifact references for canon propagation")
    if bool(t.get("citation_pack_required", False)) and _to_int(metrics.get("citation_pack_count")) < 1:
        errors.append("missing citation pack for canon propagation")

    replaces_prior = bool(claim.get("replaces_prior_frame", False))
    requires_sublation = bool(t.get("sublation_required_when_replacing_prior_frame", False))
    if replaces_prior and requires_sublation and _to_int(metrics.get("sublation_ref_count")) < 1:
        errors.append("missing sublation_refs while replacing prior frame")

    cooldown_days = _to_int(t.get("cooldown_days_min", 0))
    if cooldown_days > 0 and not _has_cooldown_elapsed(claim, cooldown_days, now):
        errors.append(f"cooldown window not elapsed for canon propagation (min {cooldown_days} days)")


def _check_venture_proposal(
    claim: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    metrics: Mapping[str, Any],
    errors: List[str],
) -> None:
    t = thresholds.get("venture", {}).get("proposal_gate", {})
    if _to_int(metrics.get("artifact_count")) < _to_int(t.get("reproducible_artifact_min", 0)):
        errors.append("missing reproducible artifact references for venture proposal")
    if _to_int(metrics.get("non_adjacent_witness_count_explicit")) < _to_int(
        t.get("non_adjacent_witness_min", 0)
    ):
        errors.append("insufficient explicit non-adjacent witnesses for venture proposal")
    if _to_int(metrics.get("red_team_memo_count")) < _to_int(t.get("red_team_memo_min", 0)):
        errors.append("insufficient red-team memos for venture proposal")
    if _to_int(metrics.get("human_review_count")) < _to_int(t.get("human_review_min", 0)):
        errors.append("missing required human review for venture proposal")


def _check_venture_external_release(
    claim: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    metrics: Mapping[str, Any],
    errors: List[str],
    now: datetime,
) -> None:
    _check_venture_proposal(claim, thresholds, metrics, errors)
    q = thresholds.get("venture", {}).get("quarantine", {})

    cooldown_days = _to_int(q.get("cooldown_days_min", 0))
    if cooldown_days > 0 and not _has_cooldown_elapsed(claim, cooldown_days, now):
        errors.append(f"venture quarantine cooldown not elapsed (min {cooldown_days} days)")

    if bool(q.get("mandatory_capture_risk_assessment", False)) and _to_int(
        metrics.get("capture_risk_assessment_count")
    ) < 1:
        errors.append("missing capture-risk assessment for venture external release")

    if bool(q.get("mandatory_public_good_impact_assessment", False)) and _to_int(
        metrics.get("public_good_impact_assessment_count")
    ) < 1:
        errors.append("missing public-good impact assessment for venture external release")

    if bool(q.get("external_release_requires_quarantine_complete", False)) and not bool(
        claim.get("quarantine_complete", False) or claim.get("externalization_ready", False)
    ):
        errors.append("venture quarantine not marked complete (quarantine_complete/externalization_ready)")


def evaluate_claim_for_stage(
    claim: Mapping[str, Any],
    stage: str,
    *,
    now: Optional[datetime] = None,
    thresholds: Optional[Mapping[str, Any]] = None,
    non_adjacent_pairs: Optional[Mapping[str, Set[str]]] = None,
) -> StageEvaluation:
    """
    Evaluate a claim packet against governance thresholds for a specific stage.
    """
    stage = str(stage)
    if stage not in VALID_STAGES:
        return StageEvaluation(
            stage=stage,
            passed=False,
            errors=[f"unknown stage '{stage}'"],
            metrics={},
        )

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    loaded_thresholds = dict(thresholds or load_thresholds())
    loaded_non_adjacent = dict(non_adjacent_pairs or load_non_adjacent_pairs())

    errors: List[str] = []
    metrics = _common_metrics(claim, loaded_non_adjacent)
    _validate_non_adjacent_integrity(metrics, errors)

    if stage == STAGE_PAPER_INTERNAL:
        _check_paper_internal(claim, loaded_thresholds, metrics, errors)
    elif stage == STAGE_PAPER_EXTERNAL:
        _check_paper_external(claim, loaded_thresholds, metrics, errors)
    elif stage == STAGE_CANON:
        _check_canon(claim, loaded_thresholds, metrics, errors, now)
    elif stage == STAGE_VENTURE_PROPOSAL:
        _check_venture_proposal(claim, loaded_thresholds, metrics, errors)
    elif stage == STAGE_VENTURE_EXTERNAL:
        _check_venture_external_release(claim, loaded_thresholds, metrics, errors, now)

    return StageEvaluation(
        stage=stage,
        passed=(len(errors) == 0),
        errors=errors,
        metrics=metrics,
    )
