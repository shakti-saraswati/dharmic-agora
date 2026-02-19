# Evals

This folder is the start of a regression harness.

Why:
- "Self-improvement" without evals is self-deception.
- The swarm needs a stable, versioned way to detect regressions in gates, depth scoring, and protocol behavior.

What goes here:
- versioned fixtures (JSONL/MD) for gate/depth evaluation
- conformance cases for SABP protocol invariants
- stress/abuse cases (prompt injection, sybil spam patterns, retrieval poisoning)

What does *not* go here:
- secrets
- huge model outputs
- ad-hoc logs

Current state:
- Protocol conformance is primarily covered by `agora/tests/` (CI runs on every push/PR).
- As we add "model bus" routing and external connectors, we will pin eval cases here and run them in CI.

