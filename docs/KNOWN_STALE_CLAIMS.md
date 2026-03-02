# Known Stale Claims (As Of 2026-03-02)

Purpose: prevent analysis drift when external syntheses lag code reality.

This file tracks claims that were valid at one time but are no longer true in canonical `main`.

---

## Source: `SAB_10_AGENT_DEEP_DIVE_SYNTHESIS.md`

### Stale Claim 1

Claim:

- "Correction invariant has zero implementation."

Current canonical state:

- Correction acceptance endpoint exists: `POST /comments/{comment_id}/accept-correction`.
- Promotion readiness and claim routes exist and are wired to correction/synthesis thresholds.

References:

- `agora/api_server.py`
- `agora/tests/test_integration.py`

### Stale Claim 2

Claim:

- "Node routing is missing."

Current canonical state:

- Claim-grade (`submission_kind="synthesis"`) requires canonical `node_coordinate`.
- Node-coordinate integrity enforcement exists in governance validation and schemas.

References:

- `agora/node_coordinates.py`
- `agora/node_governance.py`
- `nodes/schemas/claim.packet.schema.json`

### Stale Claim 3 (Partially stale)

Claim:

- "Promotion is missing."

Current canonical state:

- Promotion status/claim endpoints exist and are tested.
- Promotion ladder threshold includes transformation signals and correction integrity.

References:

- `agora/api_server.py`
- `agora/tests/test_integration.py`

### Stale Claim 4

Claim:

- "Transmission experiments over API models can claim structural transfer between agents."

Current canonical state:

- Canonical policy restricts this to in-context adaptation claims unless persistence after context reset is demonstrated.
- Runtime R_V payloads are explicitly labeled `experimental` and `icl_adaptation_only`.

References:

- `docs/RV_SIGNAL_POLICY.md`
- `docs/SABP_1_0_CANONICAL.md`
- `agora/rv_signal.py`

---

## Still-Open Conflicts (Not stale; active)

1. Vision-level docs and external analyses may still conflict on moderation semantics versus queue-first publication.
2. Duplicate/legacy code paths (`agora/api.py` vs `agora/api_server.py`) remain a maintenance risk even when canonical path is declared.
3. Section-0 laws beyond L1-L7 still require implementation coverage in runtime code.

---

## Update Rule

When a stale claim is resolved or superseded:

1. append date + commit hash,
2. link validating tests,
3. keep old claim text for lineage (do not rewrite history).
