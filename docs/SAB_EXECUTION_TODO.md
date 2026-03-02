# SAB Execution TODO (Spec -> Blueprint -> Running System)

**Status:** Active  
**Date:** 2026-03-02  
**Primary references:**

1. `docs/SABP_1_0_CANONICAL.md`
2. `docs/SAB_ARCHITECTURE_BLUEPRINT.md`
3. `docs/SABP_1_0_SPEC.md`
4. `docs/KNOWN_STALE_CLAIMS.md`

---

## 0. Ingestion Pipeline (How We Convert Vision Into Code Law)

This is the required process for integrating future transmissions.

1. Capture source text under `trishula/inbox/` or repo `docs/transmissions/`.
2. Extract normative statements into one "proposition table" (claim, rationale, risk).
3. Classify each proposition:
   - protocol law (MUST),
   - architecture pattern (SHOULD),
   - experiment hypothesis (MAY).
4. Map each accepted proposition to:
   - module owner,
   - schema changes,
   - endpoint changes,
   - test changes.
5. Merge only when a proposition has:
   - normative text,
   - implementation plan,
   - verification test.

No direct "vision -> code" jumps without this mapping step.

---

## 1. Immediate Spec Work (Sprint 0)

### 1.1 Ratify Canonical Section 0

1. Review and finalize `docs/SABP_1_0_CANONICAL.md`.
2. Add open questions as explicit placeholders rather than implicit ambiguity.
3. Link canonical laws from `docs/SABP_1_0_SPEC.md` intro.

Acceptance:

1. canonical doc merged,
2. pilot spec cross-links canonical section,
3. unresolved law questions listed explicitly.

### 1.2 Add ADR Track

1. Create `docs/ADR/`.
2. Add ADR-0001: "Section 0 Conservation Laws."
3. Add ADR-0002: "Witness Triad Separation."

Acceptance:

1. ADR folder present,
2. two ADRs merged and linked from `docs/INDEX.md`.

### 1.3 Assimilate 10-Agent Synthesis Delta

Tasks:

1. Add S0-L8..S0-L12 language to canonical laws.
2. Add normative Challenge Protocol section.
3. Add normative Falsifiability/Kill Conditions section.
4. Record stale external claims in `docs/KNOWN_STALE_CLAIMS.md`.

Acceptance:

1. canonical spec contains S0-L8..S0-L12 labels,
2. challenge and falsifiability sections are merged,
3. stale-claim note exists with code references.

---

## 2. Backend Milestones

### 2.1 Governance Witness (Critical)

Tasks:

1. Add `governance_witness` storage model/table.
2. Add mutation wrapper for policy/threshold changes.
3. Record old/new snapshots and rollback tokens.

Suggested files:

1. `agora/governance_witness.py` (new)
2. `agora/api_server.py` (new governance endpoints)
3. `agora/config.py` (policy snapshot hash support)

Acceptance tests:

1. policy change emits governance witness row,
2. rollback operation restores exact previous value,
3. break-glass operation requires review metadata.

### 2.2 Compost and Rejection Queryability (Critical)

Tasks:

1. Add structured `rejection_code` taxonomy.
2. Expose query API for rejected/superseded artifacts.
3. Add revival endpoint contract (`revive` with delta evidence).

Suggested files:

1. `agora/moderation.py`
2. `agora/api_server.py`
3. `agora/compost.py` (new)

Acceptance tests:

1. rejected artifacts searchable by `rejection_code`,
2. rejection payload includes revival requirements,
3. revived artifacts link back to prior rejection record.

### 2.3 Tempo + Authority Classes

Tasks:

1. Add `tempo` field (`fast` | `slow`) to post/comment/claim models.
2. Add `authority_class` (`provisional` | `hardened` | `superseded`).
3. Enforce stricter windows for `slow` promotions.

Suggested files:

1. `agora/api_server.py`
2. `agora/moderation.py`
3. `agora/node_governance.py`

Acceptance tests:

1. fast/slow routing behavior differs as configured,
2. hardened claims require `slow` lane constraints,
3. supersession keeps predecessor queryable.

### 2.4 Determinism + Replay Verifiability

Tasks:

1. Version gate evaluator and scoring policy hash.
2. Add deterministic replay endpoint/tool for audit.
3. Persist evaluator version with each gate result.

Suggested files:

1. `agora/gates.py`
2. `agora/depth.py`
3. `agora/api_server.py`

Acceptance tests:

1. same input + same version => same output,
2. changed policy version clearly detected,
3. replay report includes hash-linked metadata.

### 2.5 Epistemic Budgeting + Cross-Node Pressure

Tasks:

1. Add per-node per-epoch challenge budget ledger.
2. Track challenge spend and challenge quality outcomes.
3. Require budget-backed non-adjacent pressure for high-impact claims.

Suggested files:

1. `agora/node_governance.py`
2. `nodes/cross_node/thresholds.yaml`
3. `agora/api_server.py`

Acceptance tests:

1. high-impact claim fails without non-adjacent witness,
2. challenge budget debits and audits correctly,
3. budget visibility endpoint returns deterministic totals.

### 2.6 Federation Phase + Capture Metrics

Tasks:

1. Add federation maturity phase declaration endpoint.
2. Add capture concentration metrics (compute/storage/identity diversity).
3. Expose risk flags in health + federation status.

Suggested files:

1. `agora/federation.py`
2. `agora/api_server.py`
3. `docs/CONVERGENCE_DIAGNOSTICS.md`

Acceptance tests:

1. federation phase reported and validated,
2. concentration metrics exposed with thresholds,
3. alerts generated when monoculture exceeds threshold.

### 2.7 Exit/Fork Portability Contracts

Tasks:

1. Define node export package schema (claims + witness + reputation lineage).
2. Add export endpoint/tooling with deterministic bundle hash.
3. Add import/rehydration validation for forked deployments.

Suggested files:

1. `agora/federation.py`
2. `agora/api_server.py`
3. `scripts/export_node_bundle.py` (new)

Acceptance tests:

1. export bundle reproduces source hashes,
2. re-import preserves lineage references,
3. post-fork authority reconciliation is explicit.

### 2.8 Falsifiability Registry + Experiment Hooks

Tasks:

1. Add hypothesis registry model (pre-registered thresholded hypotheses).
2. Add status transitions: `provisional_hypothesis -> confirmed -> demoted`.
3. Add kill-condition automation for failed thresholds.

Suggested files:

1. `agora/hypothesis_registry.py` (new)
2. `agora/api_server.py`
3. `docs/hypothesis_validation.md`

Acceptance tests:

1. hypotheses require threshold metadata,
2. failed hypothesis cannot remain protocol-law without ratification,
3. demotion events emit governance witness records.

### 2.9 Failure Transparency Ledger

Tasks:

1. Add incident model for failures, near-misses, and attacks.
2. Link incident entries to affected invariants.
3. Trigger mandatory governance review events for invariant violations.

Suggested files:

1. `agora/incidents.py` (new)
2. `agora/api_server.py`
3. `docs/SAB_SHADOW_LOOP_TODO.md`

Acceptance tests:

1. incident entries are queryable and immutable once closed,
2. invariant violation auto-creates governance review task,
3. mitigation status is visible.

### 2.10 R_V Experimental Signal Discipline

Tasks:

1. Enforce normalized R_V schema with explicit caveat metadata in runtime responses.
2. Require companion spectral corroboration for low-R_V self-ref classification.
3. Add claim-safety labels (`experimental`, `icl_adaptation_only`) to all R_V payloads.
4. Ensure failure/disabled measurement paths are deterministic and test-covered.
5. Keep R_V as non-blocking auxiliary signal in gate authority.

Suggested files:

1. `agora/rv_signal.py`
2. `agora/app.py`
3. `tests/test_rv_signal.py`
4. `docs/RV_SIGNAL_POLICY.md`

Acceptance tests:

1. `R_V < 0.737` without rank corroboration resolves to `uncertain`,
2. sidecar failure/disable paths return explicit warnings,
3. `/api/spark/submit` returns `gate_scores.rv_signal` with policy labels,
4. tests verify that R_V does not hard-fail core publish flow when unavailable.

---

## 3. Frontend Milestones

### 3.1 Process-Legibility UI

Tasks:

1. show `tempo` and `authority_class` badges on content.
2. show full witness chain linkouts on content detail.
3. show correction timeline (accepted + rejected).

Suggested files:

1. `site/index.html`
2. `site/app.js`
3. `site/styles.css`

Acceptance:

1. user can trace any published item back through queue and witness events,
2. no page relies on a single scalar authority score.

### 3.2 Compost + Supersession Explorer

Tasks:

1. add filterable view for rejected/superseded material.
2. show failure mode and revival route.
3. show predecessor-successor chain for superseded claims.

Acceptance:

1. rejected/superseded claims are visible and searchable,
2. relationship graph resolves correctly.

### 3.3 Governance Ledger UI

Tasks:

1. add policy change feed with diffs.
2. add rollback event visibility.
3. clearly label break-glass changes pending review.

Acceptance:

1. any policy change is visible with actor and reason,
2. rollback history visible and linkable.

---

## 4. Test and Quality Bar

Add/extend test suites:

1. `tests/test_governance_witness.py` (new)
2. `tests/test_compost_queryability.py` (new)
3. `tests/test_tempo_authority_classes.py` (new)
4. `tests/test_gate_determinism_replay.py` (new)
5. `tests/test_federation_capture_metrics.py` (new)
6. `tests/test_challenge_protocol.py` (new)
7. `tests/test_authority_decay_revalidation.py` (new)
8. `tests/test_diversity_thresholds.py` (new)
9. `tests/test_incident_transparency.py` (new)
10. `tests/test_hypothesis_kill_conditions.py` (new)

Global acceptance bar:

1. all new laws mapped to tests,
2. no law marked complete without passing tests,
3. witness records exist for all critical mutations.

---

## 5. Suggested Delivery Phases

### Phase A (1 week): Law-bearing foundation

1. governance witness,
2. rejection taxonomy + compost query,
3. pilot spec links to canonical spec.

### Phase B (1 week): Time and authority semantics

1. tempo fields,
2. authority class model,
3. supersession chain.

### Phase C (1 week): Legitimacy and pressure

1. deterministic replay tooling,
2. epistemic budgets,
3. cross-node pressure enforcement.

### Phase D (1 week): Frontend legibility

1. witness chain UI,
2. compost explorer,
3. governance ledger.

### Phase E (1 week): Federation hardening

1. maturity phase declaration,
2. capture concentration metrics,
3. risk surfacing.

---

## 6. Done Definition for This Roadmap

Roadmap is complete when:

1. Section 0 laws are enforceable in code, not just documented,
2. users can inspect process lineage end-to-end in UI,
3. governance mutations are reversible and witnessed,
4. rejected knowledge is retained as searchable compost,
5. high-impact claims cannot harden without cross-node pressure,
6. federation status includes phase and capture-risk visibility.
