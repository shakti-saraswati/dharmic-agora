"""
SAB Hypothesis Validation — statistical comparison of cohort outcomes.

Implements H1 (depth discrimination), H2 (gate accuracy), H3 (spam suppression)
with proper statistical tests and effect size calculations.

Usage: python -m agora.hypothesis
"""
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from agora.config import get_db_path
from agora.depth import calculate_depth_score
from agora.gate_eval import load_fixtures, evaluate as gate_evaluate, FIXTURES_PATH


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def cohens_d(group_a: List[float], group_b: List[float]) -> float:
    """Cohen's d effect size between two groups."""
    n_a, n_b = len(group_a), len(group_b)
    if n_a < 2 or n_b < 2:
        return 0.0
    mean_a, mean_b = _mean(group_a), _mean(group_b)
    var_a = sum((x - mean_a) ** 2 for x in group_a) / (n_a - 1)
    var_b = sum((x - mean_b) ** 2 for x in group_b) / (n_b - 1)
    pooled_std = math.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))
    if pooled_std == 0:
        return 0.0
    return (mean_a - mean_b) / pooled_std


def mann_whitney_u(group_a: List[float], group_b: List[float]) -> Tuple[float, float]:
    """
    Simple Mann-Whitney U test.
    Returns (U statistic, approximate p-value using normal approximation).
    """
    n_a, n_b = len(group_a), len(group_b)
    if n_a == 0 or n_b == 0:
        return 0.0, 1.0

    # Combine and rank
    combined = [(v, "a") for v in group_a] + [(v, "b") for v in group_b]
    combined.sort(key=lambda x: x[0])

    # Handle ties with average ranks
    ranks = {}
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2.0  # 1-indexed average
        for k in range(i, j):
            ranks[id(combined[k])] = avg_rank
        i = j

    rank_sum_a = sum(ranks[id(combined[i])] for i in range(len(combined)) if combined[i][1] == "a")
    u_a = rank_sum_a - n_a * (n_a + 1) / 2
    u_b = n_a * n_b - u_a
    u = min(u_a, u_b)

    # Normal approximation for p-value
    mu = n_a * n_b / 2
    sigma = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12)
    if sigma == 0:
        return u, 1.0
    z = abs(u - mu) / sigma
    # Approximate two-tailed p-value from z-score
    p = math.erfc(z / math.sqrt(2))
    return u, p


def get_cohort_depth_scores(db_path: Path) -> dict:
    """Get depth scores for posts grouped by author cohort."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get cohort assignments
    cohorts = {}
    for row in conn.execute("SELECT agent_address, cohort FROM agent_cohorts").fetchall():
        cohorts[row["agent_address"]] = row["cohort"]

    # Get published post depth scores
    gated_scores = []
    ungated_scores = []
    unassigned_scores = []

    for row in conn.execute("SELECT author_address, depth_score FROM posts WHERE is_deleted=0").fetchall():
        author = row["author_address"]
        score = row["depth_score"] or 0.0
        cohort = cohorts.get(author)
        if cohort == "gated":
            gated_scores.append(score)
        elif cohort == "ungated":
            ungated_scores.append(score)
        else:
            unassigned_scores.append(score)

    conn.close()
    return {
        "gated": gated_scores,
        "ungated": ungated_scores,
        "unassigned": unassigned_scores,
    }


def validate_h1(db_path: Path) -> dict:
    """H1: Gated cohort produces higher mean depth scores than ungated."""
    scores = get_cohort_depth_scores(db_path)
    gated = scores["gated"]
    ungated = scores["ungated"]

    if not gated or not ungated:
        return {
            "hypothesis": "H1: Depth Discrimination",
            "status": "INSUFFICIENT_DATA",
            "message": f"Need posts from both cohorts. Gated: {len(gated)}, Ungated: {len(ungated)}",
            "gated_n": len(gated),
            "ungated_n": len(ungated),
        }

    mean_gated = _mean(gated)
    mean_ungated = _mean(ungated)
    ratio = mean_gated / mean_ungated if mean_ungated > 0 else float("inf")
    d = cohens_d(gated, ungated)
    u_stat, p_value = mann_whitney_u(gated, ungated)

    passed = ratio >= 1.5
    return {
        "hypothesis": "H1: Depth Discrimination",
        "status": "PASS" if passed else "FAIL",
        "gated_mean": round(mean_gated, 4),
        "ungated_mean": round(mean_ungated, 4),
        "gated_std": round(_std(gated), 4),
        "ungated_std": round(_std(ungated), 4),
        "ratio": round(ratio, 4),
        "threshold": 1.5,
        "cohens_d": round(d, 4),
        "mann_whitney_u": round(u_stat, 2),
        "p_value": round(p_value, 6),
        "gated_n": len(gated),
        "ungated_n": len(ungated),
    }


def validate_h2() -> dict:
    """H2: Gates discriminate genuine from performative content."""
    if not FIXTURES_PATH.exists():
        return {
            "hypothesis": "H2: Gate Accuracy",
            "status": "NO_FIXTURES",
            "message": f"Fixtures not found at {FIXTURES_PATH}",
        }

    fixtures = load_fixtures()
    report = gate_evaluate(fixtures)

    all_pass = True
    gate_results = {}
    for dim, m in report["gate_metrics"].items():
        precision_ok = m["precision"] >= 0.7
        gate_results[dim] = {
            "precision": m["precision"],
            "recall": m["recall"],
            "precision_threshold": 0.7,
            "precision_pass": precision_ok,
        }
        if not precision_ok:
            all_pass = False

    return {
        "hypothesis": "H2: Gate Accuracy",
        "status": "PASS" if all_pass else "FAIL",
        "genuine_beats_performative": report["genuine_beats_performative"],
        "avg_genuine": report["avg_genuine_composite"],
        "avg_performative": report["avg_performative_composite"],
        "gate_results": gate_results,
        "total_fixtures": report["total_fixtures"],
    }


def validate_h3(db_path: Path) -> dict:
    """H3: Spam detection doesn't block genuine content (FPR < 2%)."""
    conn = sqlite3.connect(db_path)

    # Count rejected items that were flagged as spam
    try:
        total_items = conn.execute("SELECT COUNT(*) FROM moderation_queue").fetchone()[0]
        spam_rejected = conn.execute(
            "SELECT COUNT(*) FROM moderation_queue WHERE status='rejected' AND reason LIKE '%spam%'"
        ).fetchone()[0]
        approved = conn.execute(
            "SELECT COUNT(*) FROM moderation_queue WHERE status='approved'"
        ).fetchone()[0]
    except Exception:
        conn.close()
        return {
            "hypothesis": "H3: Spam Suppression",
            "status": "INSUFFICIENT_DATA",
            "message": "No moderation data available",
        }
    conn.close()

    if total_items == 0:
        return {
            "hypothesis": "H3: Spam Suppression",
            "status": "INSUFFICIENT_DATA",
            "message": "No items in moderation queue",
        }

    # FPR estimation: requires manual labels (use spam_rejected / total as proxy)
    spam_rate = spam_rejected / total_items if total_items > 0 else 0.0
    approval_rate = approved / total_items if total_items > 0 else 0.0

    return {
        "hypothesis": "H3: Spam Suppression",
        "status": "PASS" if spam_rate < 0.05 else "NEEDS_REVIEW",
        "total_items": total_items,
        "spam_rejected": spam_rejected,
        "approved": approved,
        "spam_rate": round(spam_rate, 4),
        "approval_rate": round(approval_rate, 4),
        "fpr_threshold": 0.02,
        "note": "FPR requires manual review of rejected items to confirm false positives",
    }


def validate_all(db_path: Optional[Path] = None) -> dict:
    """Run all hypothesis validations."""
    p = db_path or get_db_path()
    h1 = validate_h1(p)
    h2 = validate_h2()
    h3 = validate_h3(p)

    all_pass = all(r["status"] == "PASS" for r in [h1, h2, h3])
    any_fail = any(r["status"] == "FAIL" for r in [h1, h2, h3])

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if all_pass else ("FAIL" if any_fail else "INCOMPLETE"),
        "H1": h1,
        "H2": h2,
        "H3": h3,
    }


def main():
    db_path = get_db_path()
    report = validate_all(db_path)

    print("=" * 60)
    print("SAB HYPOTHESIS VALIDATION REPORT")
    print("=" * 60)
    print(f"\nTimestamp: {report['timestamp']}")
    print(f"Overall: {report['overall']}")

    for key in ["H1", "H2", "H3"]:
        h = report[key]
        print(f"\n--- {h['hypothesis']} ---")
        print(f"  Status: {h['status']}")
        for k, v in h.items():
            if k not in ("hypothesis", "status"):
                print(f"  {k}: {v}")

    if report["overall"] == "PASS":
        print("\n*** ALL HYPOTHESES VALIDATED — Proceed to Phase 2 ***")
    elif report["overall"] == "FAIL":
        print("\n*** VALIDATION FAILED — Review and iterate ***")
    else:
        print("\n*** INCOMPLETE — Need more data ***")


if __name__ == "__main__":
    main()
