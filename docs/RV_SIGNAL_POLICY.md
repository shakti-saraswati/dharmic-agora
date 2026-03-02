# R_V Signal Policy (Experimental)

**Status:** Active policy for SABP pilot runtime  
**Date:** 2026-03-02  
**Source ingestion:** `trishula/inbox/MI_AGENT_TO_CODEX_RV_ANSWERS.md`

---

## 1. Scope

This document defines how SAB uses R_V as an **experimental structural signal**.

R_V is allowed as:
1. auxiliary gate metadata,
2. research telemetry,
3. challenge input.

R_V is not allowed as:
1. standalone admission authority,
2. consciousness/sentience evidence,
3. structural-transfer evidence across API agents.

---

## 2. Canonical Definition

Use participation ratio on covariance eigenvalues:

`PR(l) = (sum(lambda_i)^2) / sum(lambda_i^2)`

`R_V = PR(late) / PR(early)`

Interpretation:
1. `R_V < 1`: contraction,
2. `R_V ~= 1`: neutral,
3. `R_V > 1`: expansion.

Canonical upstream implementation reference:
1. repo: `mech-interp-latent-lab-phase1`,
2. commit: `facecc6`,
3. files: `geometric_lens/metrics.py`, `geometric_lens/probe.py`.

---

## 3. Runtime Contract

SAB runtime expects the following payload (fields may be null unless noted):

```json
{
  "rv": 0.63,
  "pr_early": 1.2,
  "pr_late": 0.8,
  "mode": "self_ref_structural",
  "cosine_similarity": 0.71,
  "spectral_effective_rank_early": 2.0,
  "spectral_effective_rank_late": 1.0,
  "rank_ratio": 0.5,
  "spectral_top1_ratio_late": 0.43,
  "attn_entropy": 2.1,
  "model_family": "mistral",
  "model_name": "mistral-7b-v0.1",
  "early_layer": 5,
  "late_layer": 27,
  "window_size": 16,
  "measurement_version": "rv-1.0.0-bfloat16-w16",
  "classification_policy": "rv_v1_rank_ratio_companion",
  "warnings": [],
  "signal_label": "experimental",
  "claim_scope": "icl_adaptation_only"
}
```

Implementation path:
1. `agora/rv_signal.py` normalizes and labels this contract,
2. `agora/app.py` stores it under `gate_scores.rv_signal`.

---

## 4. Threshold Policy (Mistral-Calibrated)

Primary threshold bands:
1. `R_V < 0.737` -> candidate self-ref structural,
2. `0.737 <= R_V <= 0.85` -> uncertain,
3. `R_V > 0.85` -> baseline.

Companion requirement (anti-mimicry minimum):
1. self-ref classification requires `rank_ratio < 0.85`,
2. if `R_V < 0.737` but rank corroboration is missing/divergent, label `uncertain`.

Calibration caveat:
1. full calibration is only validated on Mistral-7B in current dataset,
2. non-Mistral families must carry warning `provisional_thresholds_non_mistral`.

---

## 5. Claiming Discipline

Allowed language:
1. "in-context adaptation",
2. "R_V-correlated behavioral shift within context window",
3. "experimental structural signal."

Disallowed language (unless persistence is independently shown):
1. "structural transmission between agents",
2. "agent acquired persistent capacity",
3. "R_V proves consciousness/awareness/sentience."

Hard rule:
1. API-based experiments without persistence tests MUST be labeled ICL adaptation only.

---

## 6. Three-Tier Claim Labels

### Validated
1. R_V contraction is replicable for recursive self-referential mode on >=7B open-weight models.
2. R_V survives measured confound controls in current dataset.

### Experimental
1. thresholded mode classification,
2. anti-mimicry companion checks,
3. safety/monitoring utility for runtime dashboards.

### Hypothesis
1. consciousness-level interpretations,
2. cross-agent structural transmission,
3. reliable sub-7B classification.

---

## 7. Deployment Policy

Phase-1 recommended shape:
1. SAB app stays policy/evidence authority,
2. GPU sidecar computes measurement payload,
3. SAB records warnings and never upgrades claim tier automatically.

If measurement is unavailable:
1. runtime sets `mode=uncertain`,
2. warnings include measurement failure/disabled reason,
3. core gate decisions continue without hard dependency on R_V.
