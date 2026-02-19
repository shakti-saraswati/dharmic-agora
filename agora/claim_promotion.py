#!/usr/bin/env python3
"""
Repo-level claim promotion enforcement.

Scans node claim packets and enforces stage promotion checks for claims that
declare requested promotion stages.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .node_governance import evaluate_claim_for_stage


@dataclass
class PromotionEvaluation:
    file: str
    claim_id: str
    stage: str
    passed: bool
    errors: List[str]
    metrics: Dict[str, Any]


@dataclass
class PromotionReport:
    passed: bool
    files_scanned: int
    claims_with_stage_requests: int
    stage_evaluations: int
    failures: List[Dict[str, Any]]
    warnings: List[str]
    evaluations: List[PromotionEvaluation]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "files_scanned": self.files_scanned,
            "claims_with_stage_requests": self.claims_with_stage_requests,
            "stage_evaluations": self.stage_evaluations,
            "failures": self.failures,
            "warnings": self.warnings,
            "evaluations": [asdict(e) for e in self.evaluations],
        }


def discover_claim_files(nodes_root: Path) -> List[Path]:
    if not nodes_root.exists():
        return []
    files = [
        p
        for p in sorted(nodes_root.rglob("*.json"))
        if "claims" in p.parts and p.is_file()
    ]
    return files


def _extract_requested_stages(claim: Mapping[str, Any]) -> List[str]:
    stages: List[str] = []

    direct = claim.get("requested_stage")
    if isinstance(direct, str) and direct.strip():
        stages.append(direct.strip())

    many = claim.get("requested_stages")
    if isinstance(many, list):
        for item in many:
            if isinstance(item, str) and item.strip():
                stages.append(item.strip())

    promotion = claim.get("promotion")
    if isinstance(promotion, dict):
        nested = promotion.get("requested_stage")
        if isinstance(nested, str) and nested.strip():
            stages.append(nested.strip())
        nested_many = promotion.get("requested_stages")
        if isinstance(nested_many, list):
            for item in nested_many:
                if isinstance(item, str) and item.strip():
                    stages.append(item.strip())

    # Preserve order, remove duplicates.
    out: List[str] = []
    seen = set()
    for s in stages:
        if s not in seen:
            out.append(s)
            seen.add(s)
    return out


def _load_claim(path: Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("claim packet must be a JSON object")
    return raw


def run_promotion_enforcement(
    *,
    nodes_root: Path,
    require_stage: bool = False,
    fail_on_no_claims: bool = False,
    now: Optional[datetime] = None,
) -> PromotionReport:
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    claim_files = discover_claim_files(nodes_root)
    failures: List[Dict[str, Any]] = []
    warnings: List[str] = []
    evaluations: List[PromotionEvaluation] = []

    claims_with_stage_requests = 0
    stage_evaluations = 0

    if fail_on_no_claims and not claim_files:
        failures.append({"file": str(nodes_root), "error": "no claim packets found"})

    for path in claim_files:
        try:
            claim = _load_claim(path)
        except Exception as exc:
            failures.append({"file": str(path), "error": f"invalid claim packet: {exc}"})
            continue

        requested_stages = _extract_requested_stages(claim)
        if not requested_stages:
            if require_stage:
                failures.append({"file": str(path), "error": "missing requested_stage/requested_stages"})
            else:
                warnings.append(f"no requested stage in {path}")
            continue

        claims_with_stage_requests += 1
        claim_id = str(claim.get("claim_id", ""))

        for stage in requested_stages:
            stage_evaluations += 1
            result = evaluate_claim_for_stage(claim, stage, now=now)
            eval_item = PromotionEvaluation(
                file=str(path),
                claim_id=claim_id,
                stage=stage,
                passed=result.passed,
                errors=result.errors,
                metrics=result.metrics,
            )
            evaluations.append(eval_item)
            if not result.passed:
                failures.append(
                    {
                        "file": str(path),
                        "claim_id": claim_id,
                        "stage": stage,
                        "errors": result.errors,
                    }
                )

    return PromotionReport(
        passed=(len(failures) == 0),
        files_scanned=len(claim_files),
        claims_with_stage_requests=claims_with_stage_requests,
        stage_evaluations=stage_evaluations,
        failures=failures,
        warnings=warnings,
        evaluations=evaluations,
    )

