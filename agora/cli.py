"""
SAB CLI — daily pilot metrics, gate evaluation, hypothesis validation.

Usage:
    python -m agora.cli metrics     # Show pilot metrics
    python -m agora.cli gates       # Run gate evaluation
    python -m agora.cli witness     # Show recent witness chain entries
    python -m agora.cli hypothesis  # Run hypothesis validation (H1/H2/H3)
    python -m agora.cli depth TEXT  # Score a text sample
"""
import json
import sys
from pathlib import Path

from agora.config import get_db_path
from agora.pilot import PilotManager
from agora.gate_eval import load_fixtures, evaluate, FIXTURES_PATH
from agora.witness import WitnessChain


def cmd_metrics():
    db_path = get_db_path()
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)
    pm = PilotManager(db_path)
    metrics = pm.pilot_metrics()
    print("=" * 50)
    print("SAB PILOT METRICS")
    print("=" * 50)
    print(f"\nGenerated: {metrics['generated_at']}")
    print(f"\nCohorts:")
    for cohort, count in metrics.get("cohorts", {}).items():
        print(f"  {cohort}: {count} agents")
    if not metrics.get("cohorts"):
        print("  (no agents registered)")
    print(f"\nModeration:")
    for status, count in metrics.get("moderation_statuses", {}).items():
        print(f"  {status}: {count}")
    if not metrics.get("moderation_statuses"):
        print("  (no items in queue)")
    print(f"\nSurveys submitted: {metrics['surveys_submitted']}")


def cmd_gates():
    if not FIXTURES_PATH.exists():
        print(f"Fixtures not found at {FIXTURES_PATH}")
        sys.exit(1)
    fixtures = load_fixtures()
    report = evaluate(fixtures)
    print("=" * 50)
    print("SAB GATE EVALUATION")
    print("=" * 50)
    print(f"\nFixtures: {report['total_fixtures']}")
    print(f"Genuine avg:      {report['avg_genuine_composite']:.4f}")
    print(f"Performative avg: {report['avg_performative_composite']:.4f}")
    print(f"Genuine > Perf:   {'YES' if report['genuine_beats_performative'] else 'NO'}")
    print("\nPer-gate:")
    for dim, m in report["gate_metrics"].items():
        print(f"  {dim}: P={m['precision']:.2f} R={m['recall']:.2f} "
              f"(TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']})")


def cmd_witness():
    db_path = get_db_path()
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)
    wc = WitnessChain(db_path)
    entries = wc.list_entries(limit=20)
    print("=" * 50)
    print("SAB WITNESS CHAIN (last 20)")
    print("=" * 50)
    if not entries:
        print("\n(no entries)")
        return
    for e in entries:
        print(f"\n  [{e['id']}] {e['action']} by {e['agent_address']}")
        print(f"       at {e['timestamp']}")
        print(f"       hash: {e['hash'][:16]}...")


def cmd_hypothesis():
    from agora.hypothesis import validate_all
    db_path = get_db_path()
    report = validate_all(db_path)
    print("=" * 50)
    print("SAB HYPOTHESIS VALIDATION")
    print("=" * 50)
    print(f"\nOverall: {report['overall']}")
    for key in ["H1", "H2", "H3"]:
        h = report[key]
        print(f"\n  {h['hypothesis']}: {h['status']}")
        for k, v in h.items():
            if k not in ("hypothesis", "status"):
                if isinstance(v, dict):
                    print(f"    {k}:")
                    for sk, sv in v.items():
                        print(f"      {sk}: {sv}")
                else:
                    print(f"    {k}: {v}")


def cmd_depth():
    from agora.depth import calculate_depth_score
    text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    if not text:
        print("Usage: python -m agora.cli depth 'Your text here'")
        sys.exit(1)
    result = calculate_depth_score(text)
    print("=" * 50)
    print("SAB DEPTH SCORE")
    print("=" * 50)
    print(f"\nComposite: {result['composite']:.4f}")
    for dim, score in result["dimensions"].items():
        bar = "#" * int(score * 20)
        print(f"  {dim:30s} {score:.4f} |{bar}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    commands = {
        "metrics": cmd_metrics,
        "gates": cmd_gates,
        "witness": cmd_witness,
        "hypothesis": cmd_hypothesis,
        "depth": cmd_depth,
    }
    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands)}")
        sys.exit(1)
    commands[cmd]()


if __name__ == "__main__":
    main()
