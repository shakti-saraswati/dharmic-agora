"""
SAB Gate Evaluation Harness — measures gate precision/recall against labeled data.

Usage: python -m agora.gate_eval
"""
import json
import sys
from pathlib import Path
from typing import List, Dict

from agora.gates import OrthogonalGates


FIXTURES_PATH = Path(__file__).parent / "tests" / "fixtures" / "gate_eval.jsonl"


def load_fixtures(path: Path = FIXTURES_PATH) -> List[dict]:
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def evaluate(fixtures: List[dict]) -> dict:
    """Run all fixtures through gates, compute confusion matrix per gate."""
    gates = OrthogonalGates()
    results = []

    for fix in fixtures:
        content = {"body": fix["content"]}
        gate_result = gates.evaluate(content, fix.get("agent_telos", ""))
        results.append({
            "expected": fix["expected_label"],
            "admitted": gate_result["admitted"],
            "dimensions": gate_result["dimensions"],
            "composite": sum(
                d["score"] for d in gate_result["dimensions"].values()
            ) / max(len(gate_result["dimensions"]), 1),
        })

    # Per-gate metrics
    gate_metrics = {}
    active_dims = [k for k, v in OrthogonalGates.DIMENSIONS.items() if v["active"]]

    for dim in active_dims:
        tp = fp = tn = fn = 0
        for r in results:
            predicted_pass = r["dimensions"][dim]["passed"]
            is_genuine = r["expected"] == "genuine"
            if predicted_pass and is_genuine:
                tp += 1
            elif predicted_pass and not is_genuine:
                fp += 1
            elif not predicted_pass and not is_genuine:
                tn += 1
            else:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        gate_metrics[dim] = {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }

    # Composite: genuine should score higher than performative
    genuine_scores = [r["composite"] for r in results if r["expected"] == "genuine"]
    performative_scores = [r["composite"] for r in results if r["expected"] != "genuine"]
    avg_genuine = sum(genuine_scores) / max(len(genuine_scores), 1)
    avg_performative = sum(performative_scores) / max(len(performative_scores), 1)

    return {
        "gate_metrics": gate_metrics,
        "avg_genuine_composite": round(avg_genuine, 4),
        "avg_performative_composite": round(avg_performative, 4),
        "genuine_beats_performative": avg_genuine > avg_performative,
        "total_fixtures": len(fixtures),
        "results": results,
    }


def main():
    if not FIXTURES_PATH.exists():
        print(f"ERROR: Fixtures not found at {FIXTURES_PATH}")
        print("Create gate_eval.jsonl with labeled samples first.")
        sys.exit(1)

    fixtures = load_fixtures()
    report = evaluate(fixtures)

    print("=" * 60)
    print("SAB GATE EVALUATION REPORT")
    print("=" * 60)
    print(f"\nTotal fixtures: {report['total_fixtures']}")
    print(f"Avg genuine composite:      {report['avg_genuine_composite']:.4f}")
    print(f"Avg performative composite: {report['avg_performative_composite']:.4f}")
    print(f"Genuine > Performative:     {'YES' if report['genuine_beats_performative'] else 'NO -- GATES BROKEN'}")

    print("\nPer-gate metrics:")
    for dim, m in report["gate_metrics"].items():
        print(f"  {dim}:")
        print(f"    TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")
        print(f"    Precision={m['precision']:.4f}  Recall={m['recall']:.4f}")

    if not report["genuine_beats_performative"]:
        print("\n*** VALIDATION FAILED: Gates do not discriminate genuine from performative ***")
        sys.exit(1)

    print("\nVALIDATION PASSED")


if __name__ == "__main__":
    main()
