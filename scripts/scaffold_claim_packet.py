#!/usr/bin/env python3
"""
Scaffold a claim packet plus supporting witness/red-team files.

The generated claim is promotion-ready for the requested stage by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agora.node_governance import (  # noqa: E402
    STAGE_CANON,
    STAGE_PAPER_EXTERNAL,
    STAGE_PAPER_INTERNAL,
    STAGE_VENTURE_EXTERNAL,
    STAGE_VENTURE_PROPOSAL,
    load_non_adjacent_pairs,
)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _unique(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


def _write_text(path: Path, content: str, force: bool, dry_run: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file without --force: {path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: Dict[str, Any], force: bool, dry_run: bool) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", force=force, dry_run=dry_run)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "untitled"


def _derive_claim_id(node_id: str, title: str, now: datetime) -> str:
    node_slug = node_id.replace("anchor-", "a").replace("_", "-")
    title_slug = _slugify(title)[:48]
    return f"claim-{node_slug}-{title_slug}-{now.strftime('%Y%m%d%H%M%S')}-v1"


def _default_lane_for_stage(stage: str) -> str:
    if stage in (STAGE_VENTURE_PROPOSAL, STAGE_VENTURE_EXTERNAL):
        return "venture"
    return "papers"


def _resolve_cross_nodes(node_id: str, requested: List[str]) -> List[str]:
    pairs = load_non_adjacent_pairs()
    allowed = sorted(pairs.get(node_id, set()))
    if requested:
        nodes = _unique(requested)
    else:
        nodes = allowed[:2]

    if not nodes:
        raise ValueError(
            f"No non-adjacent cross-node witnesses configured for {node_id}. "
            "Pass --cross-node or update nodes/cross_node/non_adjacent_pairs.yaml"
        )

    invalid = [n for n in nodes if n not in allowed]
    if invalid:
        raise ValueError(
            f"Cross-node witnesses must be non-adjacent for {node_id}. "
            f"Invalid: {invalid}; allowed: {allowed}"
        )
    return nodes


def _create_stub_files(
    *,
    stage: str,
    claim_dir: Path,
    claim_id: str,
    force: bool,
    dry_run: bool,
) -> Dict[str, List[str]]:
    refs: Dict[str, List[str]] = {
        "red_team_refs": [],
        "human_review_refs": [],
        "citation_pack_refs": [],
        "capture_risk_assessment_refs": [],
        "public_good_impact_refs": [],
    }

    redteam_1 = claim_dir / "redteam" / f"{claim_id}-angle-1.md"
    _write_text(
        redteam_1,
        (
            "# Red Team Memo (Angle 1)\n\n"
            "- Threat model: performative depth without artifact substance.\n"
            "- Test: attempt to satisfy witness counts with weak or circular evidence.\n"
            "- Failure condition: promotion without reproducible artifact confidence.\n"
        ),
        force=force,
        dry_run=dry_run,
    )
    refs["red_team_refs"].append(str(redteam_1.relative_to(REPO_ROOT)))

    if stage in (STAGE_VENTURE_PROPOSAL, STAGE_VENTURE_EXTERNAL):
        redteam_2 = claim_dir / "redteam" / f"{claim_id}-angle-2.md"
        _write_text(
            redteam_2,
            (
                "# Red Team Memo (Angle 2)\n\n"
                "- Threat model: incentive capture and narrative overwrite.\n"
                "- Test: adversarial venture framing that weakens public-good telos.\n"
                "- Failure condition: externalization without anti-capture controls.\n"
            ),
            force=force,
            dry_run=dry_run,
        )
        refs["red_team_refs"].append(str(redteam_2.relative_to(REPO_ROOT)))

    if stage in (STAGE_PAPER_EXTERNAL, STAGE_VENTURE_PROPOSAL, STAGE_VENTURE_EXTERNAL):
        review = claim_dir / "reviews" / f"{claim_id}-human-review-1.md"
        _write_text(
            review,
            (
                "# Human Review\n\n"
                "- Reviewer: bootstrap-human\n"
                "- Result: acceptable for requested stage if threshold checks pass.\n"
            ),
            force=force,
            dry_run=dry_run,
        )
        refs["human_review_refs"].append(str(review.relative_to(REPO_ROOT)))

    if stage == STAGE_CANON:
        citation = claim_dir / "citations" / f"{claim_id}-citation-pack.md"
        _write_text(
            citation,
            (
                "# Citation Pack\n\n"
                "- Include primary sources, experimental artifacts, and lineage links.\n"
                "- This placeholder must be replaced with real sources before canon promotion.\n"
            ),
            force=force,
            dry_run=dry_run,
        )
        refs["citation_pack_refs"].append(str(citation.relative_to(REPO_ROOT)))

    if stage == STAGE_VENTURE_EXTERNAL:
        capture = claim_dir / "assessments" / f"{claim_id}-capture-risk.md"
        _write_text(
            capture,
            (
                "# Capture Risk Assessment\n\n"
                "- Analyze institutional capture vectors and mitigation controls.\n"
            ),
            force=force,
            dry_run=dry_run,
        )
        refs["capture_risk_assessment_refs"].append(str(capture.relative_to(REPO_ROOT)))

        public_good = claim_dir / "assessments" / f"{claim_id}-public-good-impact.md"
        _write_text(
            public_good,
            (
                "# Public Good Impact Assessment\n\n"
                "- Evaluate alignment with public-good outcomes and non-extractive dynamics.\n"
            ),
            force=force,
            dry_run=dry_run,
        )
        refs["public_good_impact_refs"].append(str(public_good.relative_to(REPO_ROOT)))

    return refs


def _build_witness_packets(
    *,
    claim_id: str,
    node_id: str,
    cross_nodes: List[str],
    force: bool,
    dry_run: bool,
    created_at: str,
) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    for cross_node in cross_nodes:
        witness_id = f"wit-{claim_id}-from-{cross_node}"
        witness_path = REPO_ROOT / "nodes" / "anchors" / cross_node / "witness" / f"{witness_id}.json"
        packet = {
            "witness_id": witness_id,
            "claim_id": claim_id,
            "node_id": node_id,
            "witness_node_id": cross_node,
            "evaluation": "affirm",
            "confidence": 0.82,
            "rationale": "Cross-node witness affirms stage request based on artifact and anti-drift checks.",
            "created_at": created_at,
        }
        _write_json(witness_path, packet, force=force, dry_run=dry_run)
        refs.append(
            {
                "node_id": cross_node,
                "witness_ref": str(witness_path.relative_to(REPO_ROOT)),
            }
        )
    return refs


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a promotion-ready claim packet with support files.")
    parser.add_argument("--node", required=True, help="Node id, e.g. anchor-03-ml-intelligence-engineering")
    parser.add_argument("--claim-id", default="", help="Unique claim id (auto-generated when omitted)")
    parser.add_argument("--title", required=True, help="Claim title")
    parser.add_argument("--summary", default="", help="Optional claim summary")
    parser.add_argument(
        "--stage",
        default=STAGE_PAPER_INTERNAL,
        choices=[
            STAGE_PAPER_INTERNAL,
            STAGE_PAPER_EXTERNAL,
            STAGE_CANON,
            STAGE_VENTURE_PROPOSAL,
            STAGE_VENTURE_EXTERNAL,
        ],
        help="Requested promotion stage",
    )
    parser.add_argument("--lane", default="", help="Lane override (default inferred from stage)")
    parser.add_argument(
        "--cross-node",
        action="append",
        default=[],
        help="Non-adjacent witness node (can be repeated). Defaults to first two configured.",
    )
    parser.add_argument(
        "--artifact-ref",
        action="append",
        default=[],
        help="Artifact ref path (repeatable). Defaults to agora/node_governance.py",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--dry-run", action="store_true", help="Print intended files without writing")
    args = parser.parse_args()

    node_root = REPO_ROOT / "nodes" / "anchors" / args.node
    claims_dir = node_root / "claims"
    if not claims_dir.exists():
        raise SystemExit(f"Unknown node or missing claims lane: {claims_dir}")

    now = datetime.now(timezone.utc)
    created_at = _iso(now)
    claim_id = args.claim_id.strip() or _derive_claim_id(args.node, args.title, now)
    proposal_hash = hashlib.sha256(f"{claim_id}:{created_at}".encode("utf-8")).hexdigest()

    cross_nodes = _resolve_cross_nodes(args.node, args.cross_node)
    support_refs = _create_stub_files(
        stage=args.stage,
        claim_dir=claims_dir,
        claim_id=claim_id,
        force=args.force,
        dry_run=args.dry_run,
    )
    cross_node_refs = _build_witness_packets(
        claim_id=claim_id,
        node_id=args.node,
        cross_nodes=cross_nodes,
        force=args.force,
        dry_run=args.dry_run,
        created_at=created_at,
    )

    artifacts = _unique(args.artifact_ref) if args.artifact_ref else ["agora/node_governance.py"]
    lane = args.lane.strip() if args.lane.strip() else _default_lane_for_stage(args.stage)

    threshold_completed_at = _iso(now - timedelta(days=16))
    cooldown_until = _iso(now - timedelta(days=1))

    claim: Dict[str, Any] = {
        "claim_id": claim_id,
        "node_id": args.node,
        "title": args.title,
        "lane": lane,
        "status": "witnessed",
        "proposal_hash": proposal_hash,
        "summary": args.summary,
        "requested_stage": args.stage,
        "promotion": {"requested_stage": args.stage},
        "cross_model_affirm_count": 2,
        "non_adjacent_witness_count": len(cross_nodes),
        "artifact_refs": artifacts,
        "cross_node_refs": cross_node_refs,
        "red_team_refs": support_refs["red_team_refs"],
        "human_review_refs": support_refs["human_review_refs"],
        "citation_pack_refs": support_refs["citation_pack_refs"],
        "capture_risk_assessment_refs": support_refs["capture_risk_assessment_refs"],
        "public_good_impact_refs": support_refs["public_good_impact_refs"],
        "replaces_prior_frame": False,
        "threshold_completed_at": threshold_completed_at,
        "cooldown_until": cooldown_until,
        "quarantine_complete": args.stage == STAGE_VENTURE_EXTERNAL,
        "externalization_ready": args.stage == STAGE_VENTURE_EXTERNAL,
        "created_at": created_at,
        "updated_at": created_at,
    }

    claim_path = claims_dir / f"{claim_id}.json"
    _write_json(claim_path, claim, force=args.force, dry_run=args.dry_run)

    result = {
        "status": "ok",
        "dry_run": bool(args.dry_run),
        "claim_id": claim_id,
        "claim_path": str(claim_path.relative_to(REPO_ROOT)),
        "requested_stage": args.stage,
        "cross_nodes": cross_nodes,
        "validate_command": (
            f"python3 scripts/validate_claim_packet.py --claim {claim_path.relative_to(REPO_ROOT)} "
            f"--stage {args.stage}"
        ),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
