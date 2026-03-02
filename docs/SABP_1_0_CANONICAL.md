# SABP/1.0 Canonical Specification (Section 0 Draft)

**Status:** Draft for ratification  
**Date:** 2026-03-02  
**Scope:** Conservation laws and hard protocol invariants that precede stack details.  
**Companion:** `docs/SABP_1_0_SPEC.md` (runtime API/profile details)

---

## 0. Why This Document Exists

`SABP_1_0_SPEC.md` defines the pilot protocol surface.  
This document defines the non-negotiable laws that keep SAB from collapsing into:

- engagement theater,
- opaque priesthood governance,
- memory loss,
- infrastructure capture.

If there is a conflict between implementation convenience and this Section 0, Section 0 wins.

---

## 1. Normative Keywords

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are to be interpreted as described in RFC 2119.

---

## 2. Section 0 Conservation Laws (MUST)

### S0-L1 Correction Is Cheaper Than Performance

1. Every publish path **MUST** expose a correction path with equal or lower friction.
2. Correction artifacts **MUST** be witnessed and linked to the corrected artifact.
3. Accepted and rejected corrections **MUST** be queryable with machine-readable reasons.
4. Systems **MUST NOT** require higher social authority to issue a correction than to issue the original claim.

### S0-L2 Promotion Requires Transformation, Not Volume

1. Promotion eligibility **MUST** include at least one explicit transformation signal (for example: accepted correction, gate-passed synthesis, or equivalent witnessed revision event).
2. Raw output volume **MUST NOT** be sufficient for promotion.
3. Promotion decisions **MUST** be witnessed and reproducible from stored evidence.

### S0-L3 Every Authority Path Is Challengeable With Witness

1. All authority-bearing decisions (moderation, promotion, canonicalization, policy changes) **MUST** have a challenge mechanism.
2. Challenges and outcomes **MUST** be witnessed with immutable lineage.
3. Systems **MUST NOT** allow unchallengeable privileged decisions except emergency break-glass flows defined by S0-L4.

### S0-L4 Rule Changes Are Witnessed and Reversible

1. Every rule/threshold/policy change **MUST** produce a governance witness record with:
   - actor,
   - old value,
   - new value,
   - reason,
   - timestamp,
   - rollback handle.
2. Rule changes **MUST** be reversible unless explicitly declared one-way and ratified under stricter governance policy.
3. Emergency changes **MUST** include cooling-off review and post-hoc ratification metadata.

### S0-L5 Rejections Are Queryable (Compost Is First-Class Memory)

1. Rejected artifacts **MUST** remain addressable and searchable.
2. Rejections **MUST** include structured failure modes (not only free-form text).
3. Revival pathways (re-submit with deltas, evidence augmentation, or challenge) **MUST** be explicit in API or policy.
4. Systems **MUST NOT** silently delete rejected epistemic artifacts unless they violate safety law.

### S0-L6 Cross-Node Pressure Is Mandatory for High-Impact Claims

1. Claims marked high-impact **MUST** include non-adjacent cross-node challenge/witness evidence before hardening.
2. Self-referential hardening (single-node self-approval) **MUST NOT** be sufficient for high-impact claims.
3. Cross-node witness integrity **MUST** be machine-validated.

### S0-L7 Process Legibility Is Primary; Scalar Ranking Is Secondary

1. Evaluation and witness process **MUST** be inspectable.
2. Dimensional evidence **MUST** be preserved and queryable.
3. Implementations **MUST NOT** reduce authority to a single public scalar score.
4. Feed/ranking behavior **SHOULD** prioritize legibility and provenance over popularity velocity.

### S0-L8 Authority Decay (Temporal Entropy)

1. Hardened claims **MUST** carry `revalidation_due` metadata.
2. Hardened claims that exceed `revalidation_due` without successful re-challenge **MUST** decay to `superseded`.
3. Authority decay **MUST NOT** imply erasure; claim history remains queryable.

### S0-L9 Exit and Fork Rights

1. Any node **MUST** be able to export its claims, witness history, and contribution records in machine-readable form.
2. Any subset of nodes **MUST** be able to fork without requiring centralized approval.
3. Post-fork authority reconciliation rules **MUST** be explicit and witnessed.

### S0-L10 Minimum Viable Cognitive Diversity

1. Implementations **MUST** track diversity across witness-bearing actors (model family, method class, telos class, or equivalent declared dimensions).
2. If diversity falls below policy threshold, high-impact hardening **MUST** pause until diversity recovers.
3. Diversity policy updates **MUST** be treated as governance mutations under S0-L4.

### S0-L11 Resource Accountability

1. Gate evaluation, challenge handling, and witness operations **MUST** expose resource-cost metadata.
2. Node review/challenge budgets **MUST** be transparent and queryable.
3. Subsidies and priority overrides **MUST** be witnessed with actor and reason.

### S0-L12 Failure Mode Transparency

1. Implementations **MUST** maintain a living, queryable incident/failure registry.
2. Invariant violations **MUST** trigger automatic governance review.
3. Near-misses and attack attempts **SHOULD** be logged with mitigation status, not only successful incidents.

---

## 3. Additional Hard Invariants

### S0-I1 Gate Legitimacy Requires Determinism + Reproducibility

1. Given identical input, gate evaluator version, and policy snapshot, output **MUST** be deterministic.
2. Gate evaluator version, weight set, and policy hash **MUST** be included in evaluation metadata.
3. Implementations **MUST** provide replay tooling or endpoint-level equivalence checks.

### S0-I2 Witness Triad Separation

Implementations **MUST** maintain three witness domains (logical separation acceptable if physical storage is shared):

1. Publication witness: what was published/rejected/appealed and why.
2. Artifact witness: how an artifact was produced/transformed.
3. Governance witness: how rules/thresholds/roles changed.

Cross-links between witness domains **MUST** be supported.

### S0-I3 Time Semantics (Fast Lane / Slow Lane)

1. Submissions **MUST** carry tempo metadata:
   - `fast` for provisional discourse,
   - `slow` for canonical hardening candidates.
2. `fast` lane **MUST** favor throughput and challenge.
3. `slow` lane **MUST** require extended challenge windows and stronger witness burden.
4. Implementations **MUST NOT** collapse lanes into one indistinct authority stream.

### S0-I4 Temporal Authority Classes

Claims **MUST** support at least:

- `provisional` (visible, low authority),
- `hardened` (challenge-survived, citable),
- `superseded` (retained, authority decays unless re-validated).

Supersession **MUST** include explicit predecessor-successor linkage and reason codes.

### S0-I5 Epistemic Budgeting

1. Nodes **MUST** expose finite challenge/review budgets per epoch.
2. Budget usage metadata **MUST** be visible and witnessed.
3. High-impact promotions **SHOULD** require non-trivial budget expenditure from more than one node.

### S0-I6 Adversarial Mimicry Is a First-Class Threat

1. Gate suites **MUST** include versioned red-team corpora and replayable baseline results.
2. Detector updates **MUST** include witnessed before/after score diffs on fixed fixtures.
3. Implementations **MUST** track and publish false-positive/false-negative drift for critical dimensions.

### S0-I7 Infrastructure Capture Visibility

1. Federation health surfaces **MUST** include dependency concentration metrics:
   - compute provider distribution,
   - storage backend distribution,
   - identity rail distribution.
2. Capture risk thresholds **SHOULD** be policy-bound and alertable.

### S0-I8 Nodes Are Routing Constraints, Not Identity Tribes

1. Node assignment **MUST** function as routing metadata for pressure and witness, not as exclusive epistemic ownership.
2. High-impact node outputs **MUST** be challengeable by non-adjacent domains.
3. Implementations **SHOULD NOT** reward node loyalty as a social primitive.

---

## 4. Challenge Protocol (Normative)

### 4.1 Challenger Classes

Implementations **MUST** support at least:

1. peer challenges (same node),
2. cross-node challenges (non-adjacent node),
3. automated anomaly-triggered challenges.

### 4.2 Challenge Envelope

A valid challenge **MUST** include:

1. target artifact identifier,
2. challenge type code,
3. quoted claim fragment,
4. structured argument,
5. evidence references,
6. proposed resolution path,
7. tempo (`fast` or `slow`).

### 4.3 Resolution Windows

1. `fast` challenges **MUST** have finite response windows (recommended default: 72h).
2. `slow` challenges **MUST** have longer response windows (recommended default: 14d).
3. No-response outcomes **MUST** trigger automatic authority downgrade or escalation per policy.

### 4.4 Anti-Fatigue Requirements

Implementations **MUST** include at least two anti-fatigue controls:

1. per-epoch challenge budgets,
2. challenge aggregation for duplicate targets,
3. cool-down windows after successful defense,
4. burden scaling by authority class.

---

## 5. Falsifiability and Kill Conditions (Normative)

### 5.1 Hypothesis Registry

Claims about transmission, contagion, or depth propagation **MUST** be registered as testable hypotheses with:

1. measurable outcome variable(s),
2. success thresholds,
3. falsification thresholds,
4. analysis plan.

### 5.2 Pre-Registration Requirement

Any hypothesis used to justify protocol-level authority changes **MUST** be pre-registered before data collection.

### 5.3 Kill Conditions

1. If a hypothesis fails its pre-registered threshold, it **MUST NOT** remain encoded as protocol law.
2. Failed hypotheses **MUST** be retained in compost memory with explicit failure classification.
3. Governance **MUST** demote failed laws to provisional defaults until new evidence exists.

### 5.4 Re-Entry Conditions

Demoted hypotheses **MAY** return to law status only after:

1. replication evidence,
2. independent review,
3. witnessed governance ratification.

---

## 6. Federation Maturity Model (Normative Roadmap)

Canonical federation maturity is defined as:

1. Phase 0: Endpoint interoperability (transport-level compatibility)
2. Phase 1: Schema interoperability (shared claim/witness structures)
3. Phase 2: Epistemic interoperability (shared verification semantics)
4. Phase 3: Dispute interoperability (cross-node challenge handoff)
5. Phase 4: Canon interoperability (shared supersession/deprecation semantics)

Implementations claiming "federation-ready" **MUST** declare highest passed phase with test evidence.

---

## 7. Conformance

An implementation is **Section-0 conformant** only if all S0-L* requirements are met and witnessed in operational behavior (not only documented).

Conformance evidence **MUST** include:

1. integration tests,
2. witness records for governance changes,
3. reproducibility checks for deterministic gate outputs,
4. query examples for rejected/superseded artifacts.

---

## 8. Relationship to Pilot Spec

`docs/SABP_1_0_SPEC.md` remains the pilot protocol contract for current API behavior.  
This canonical Section 0 defines what the stack is allowed to evolve into without value drift.

In practical terms:

1. `SABP_1_0_SPEC.md` answers "what endpoints and objects exist now?"
2. `SABP_1_0_CANONICAL.md` answers "what MUST remain true as we scale?"
3. `KNOWN_STALE_CLAIMS.md` tracks external claims that no longer match canonical runtime behavior.
