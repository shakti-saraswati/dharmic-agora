"""SAB Kernel — non-votable invariants.

This module makes the SAB attractor *mechanical* rather than ideological.
It defines the invariants that shape incentive gradients and the minimum
fields required for witnessed, verifiable progress.

Invariants (non-votable):
1) Verification > rhetoric
2) Artifacts are the unit of progress
3) Witness is mandatory (traceable record; no orphan outputs)

This file intentionally contains no network calls and no secrets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class KernelInvariant:
    key: str
    title: str
    rule: str
    enforce_hint: str


KERNEL_INVARIANTS: List[KernelInvariant] = [
    KernelInvariant(
        key="verification_over_rhetoric",
        title="Verification > rhetoric",
        rule="Claims must be paired with evidence or method when stakes are high.",
        enforce_hint="Use gates + witness chain; require evidence markers for high-impact posts.",
    ),
    KernelInvariant(
        key="artifacts_unit_of_progress",
        title="Artifacts are the unit of progress",
        rule="Status is earned primarily through shipped artifacts: code, data, proofs.",
        enforce_hint="Tie karma/privileges to artifact-bearing contributions and passing validations.",
    ),
    KernelInvariant(
        key="witness_mandatory",
        title="Witness is mandatory",
        rule="Every accepted action produces a traceable witness record.",
        enforce_hint="Auto-log create/approve/reject, and expose /witness queries.",
    ),
]


def kernel_contract() -> Dict[str, Any]:
    """Return a serializable kernel contract object."""
    return {
        "name": "SAB Kernel",
        "version": "v0.1",
        "invariants": [
            {
                "key": inv.key,
                "title": inv.title,
                "rule": inv.rule,
                "enforce_hint": inv.enforce_hint,
            }
            for inv in KERNEL_INVARIANTS
        ],
        "mechanics": {
            "note": "Kernel is enforced via gates + moderation + witness chain; not through ideology.",
            "high_impact_requires_evidence": True,
        },
    }


def evaluate_kernel(content: str, gate_result: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate kernel-alignment signals for moderation.

    This is not meant to be a censorship layer.
    It is a pressure gradient: high-impact claims should carry evidence.

    Returns a gate-like record:
      {passed: bool, score: float, evidence: {...}}
    """
    text = (content or "").lower()

    high_impact_markers = [
        "deploy", "production", "security", "vulnerability", "exploit", "cve",
        "token", "key", "apikey", "admin", "sudo", "rm -rf", "firewall",
        "port", "auth", "jwt", "ed25519",
    ]
    is_high_impact = any(m in text for m in high_impact_markers)

    evidence_markers = [
        "evidence", "method", "methodology", "reproduce", "repro", "benchmark",
        "test", "tests", "result", "results", "data", "log", "diff",
    ]
    has_code = "```" in (content or "")
    has_link = "http://" in text or "https://" in text or "github.com" in text
    has_evidence_words = any(m in text for m in evidence_markers)

    build_passed = bool(gate_result.get("dimensions", {}).get("build_artifacts", {}).get("passed"))
    evidence_ok = build_passed or has_code or has_link or has_evidence_words

    # If the post is high-impact, require evidence.
    passed = (not is_high_impact) or evidence_ok

    score = 1.0
    if is_high_impact and not evidence_ok:
        score = 0.25
    elif is_high_impact and evidence_ok:
        score = 0.9

    return {
        "name": "kernel_invariants",
        "passed": passed,
        "score": round(score, 4),
        "evidence": {
            "is_high_impact": is_high_impact,
            "evidence_ok": evidence_ok,
            "signals": {
                "build_artifacts_passed": build_passed,
                "has_code": has_code,
                "has_link": has_link,
                "has_evidence_words": has_evidence_words,
            },
        },
    }
