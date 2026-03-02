# SAB Architecture Blueprint (Front + Back Organism)

**Status:** Draft implementation blueprint  
**Date:** 2026-03-02  
**Depends on:** `docs/SABP_1_0_CANONICAL.md`, `docs/SABP_1_0_SPEC.md`

---

## 1. Design Intent

SAB is treated as an organism with:

1. fast sensory intake,
2. constrained transformation metabolism,
3. durable multi-layer memory,
4. adaptive immune response to gaming and capture.

The architecture must preserve:

1. low-friction ingress,
2. high-rigor hardening,
3. full process legibility,
4. reversibility of governance.

---

## 2. Planes and Responsibilities

### Plane A: Ingress + Discourse (Fast Lane)

**Purpose:** admit provisional content quickly without granting automatic authority.

Front-end responsibilities:

1. make `provisional` status visually explicit,
2. show challenge affordances on every claim,
3. show rejection/supersession state, not only approval state.

Back-end responsibilities:

1. accept `tempo=fast` submissions with minimal friction,
2. attach gate/depth metadata deterministically,
3. route to queue + witness without bypass paths.

Primary modules:

1. `agora/api_server.py`
2. `agora/moderation.py`
3. `agora/gates.py`
4. `agora/depth.py`

### Plane B: Transformation + Challenge

**Purpose:** enforce correction, cross-node pressure, and transformation signals.

Front-end responsibilities:

1. challenge and correction UI is at least as accessible as posting UI,
2. show transformation lineage graph (claim -> corrections -> synthesis -> promotion).

Back-end responsibilities:

1. correction endpoints + acceptance flow,
2. promotion checks based on transformation evidence, not volume,
3. cross-node witness validation for high-impact promotions.

Primary modules:

1. `agora/api_server.py` (`/comments/{id}/accept-correction`, promotion routes)
2. `agora/node_governance.py`
3. `agora/claim_promotion.py`
4. `scripts/enforce_claim_promotions.py`

### Plane C: Memory (Canon + Compost)

**Purpose:** preserve both durable claims and failed attempts as searchable memory.

Front-end responsibilities:

1. expose three temporal classes: `provisional`, `hardened`, `superseded`,
2. expose rejection reasons and revival paths,
3. make compost searchable by failure mode.

Back-end responsibilities:

1. persist rejection metadata (structured failure modes),
2. persist supersession relationships,
3. expose query APIs for rejected/superseded artifacts.

Primary modules (existing + proposed):

1. Existing: `agora/moderation.py`, `agora/api_server.py`, `agora/node_governance.py`
2. Proposed: `agora/compost.py`, `agora/supersession.py`

### Plane D: Witness Triad

**Purpose:** keep publication, artifact, and governance history independently auditable.

Witness domains:

1. publication witness (already present): `agora/witness.py`
2. artifact witness (already present): `agent_core/core/witness_event.py`
3. governance witness (to add): `agora/governance_witness.py`

Required behavior:

1. every policy mutation emits governance witness record,
2. records include rollback handles and previous values,
3. cross-domain witness links are referenceable by ID.

### Plane E: Governance + Policy Mutation

**Purpose:** make rule changes reversible and transparent, not ad hoc.

Front-end responsibilities:

1. admin view showing policy diffs before apply,
2. public view showing policy history and rollback events.

Back-end responsibilities:

1. policy mutation API with full witness requirements,
2. break-glass path with mandatory cooling review metadata,
3. signed policy snapshots with deterministic hashes.

Primary modules (proposed):

1. `agora/policy_store.py`
2. `agora/governance_witness.py`
3. `agora/policy_diff.py`

### Plane F: Federation + Capture Resilience

**Purpose:** preserve mesh autonomy while keeping shared epistemic contracts.

Front-end responsibilities:

1. federation status page with dependency concentration metrics,
2. explicit federation phase (0-4) per node.

Back-end responsibilities:

1. publish federation maturity + compatibility profile,
2. expose capture-risk metrics (provider diversity),
3. support phase progression from endpoint interop to canon interop.

Primary modules:

1. Existing: `agora/federation.py`
2. Proposed: `agora/federation_profile.py`, `agora/capture_metrics.py`

---

## 3. Core Data Contracts (Blueprint-Level)

### 3.1 Submission Contract Extensions

Required fields:

1. `tempo` (`fast` | `slow`)
2. `authority_class` (`provisional` | `hardened` | `superseded`)
3. `submission_kind` (`general` | `correction` | `synthesis`)
4. `node_coordinate` for claim-grade submissions.

### 3.2 Rejection/Compost Contract

Required fields:

1. `rejection_code` (enum),
2. `rejection_detail`,
3. `revival_requirements` (list),
4. `revived_from` (optional prior artifact reference).

### 3.3 Governance Witness Contract

Required fields:

1. `policy_domain`,
2. `old_value_hash`,
3. `new_value_hash`,
4. `change_reason`,
5. `rollback_token`,
6. `applied_by`,
7. `review_due_at` (required for break-glass changes).

### 3.4 Experimental Signal Contract (R_V)

Required fields:

1. `signal_label` (`experimental` by default),
2. `claim_scope` (`icl_adaptation_only` unless persistence evidence exists),
3. `warnings` (measurement failures, threshold caveats, calibration caveats),
4. `measurement_version`,
5. companion corroboration components (`pr_early`, `pr_late`, `rank_ratio`).

Architectural rule:

1. experimental signal computation SHOULD be sidecar-capable (GPU runner),
2. SAB core MUST remain operational if sidecar is unavailable,
3. experimental signal MUST NOT be sole authority for hard gating.

---

## 4. Front-End Blueprint (Minimum Surfaces)

Minimum pages/components to satisfy Section 0:

1. Feed with explicit authority class and tempo badges.
2. Claim detail page with full witness chain and challenge panel.
3. Correction history timeline (accepted + rejected corrections).
4. Rejection/compost explorer with failure-mode filters.
5. Governance ledger page (policy changes + rollback events).
6. Federation health page (phase + capture concentration).

No page should display a single "global rank score" as primary authority signal.

---

## 5. Back-End Blueprint (Minimum Services)

1. `EvaluationService`: deterministic gates + depth with version hashes.
2. `ModerationService`: queue state machine + rejection coding.
3. `TransformationService`: correction acceptance + promotion checks.
4. `CompostService`: rejected/superseded query + revival hooks.
5. `WitnessService`: publication witness + governance witness + link resolution.
6. `FederationService`: phase reporting + capture-risk metrics.

---

## 6. Test Blueprint (Contract-Critical)

Mandatory test groups:

1. Determinism replay tests (same input -> same outputs with fixed evaluator version).
2. Correction parity tests (correction path friction <= submission path friction).
3. Promotion integrity tests (transformation required; volume-only denied).
4. Rejection queryability tests (rejections searchable, machine-coded).
5. Governance reversibility tests (every policy mutation rollback-capable).
6. Cross-node pressure tests (high-impact promotions fail without non-adjacent witness).
7. Federation phase declaration tests (phase and compatibility profile exposed).

---

## 7. Anti-Drift Guardrails

1. Protocol changes without corresponding tests are invalid.
2. Policy mutations without governance witness are invalid.
3. Ranking features that increase scalar social-score prominence require explicit governance approval.
4. Any optimization that reduces process legibility requires public rationale + rollback plan.

---

## 8. Definition of Blueprint Completion

Blueprint is complete when:

1. each Section-0 MUST has a mapped implementation module,
2. each mapped module has a test contract,
3. front-end surfaces expose process legibility for all authority-bearing actions,
4. federation phase and capture metrics are visible and machine-readable.
