# SAB Hypothesis Validation Framework

## Core Hypotheses

### H1: Depth Discrimination

**Statement**: Gated cohort produces higher mean depth scores than ungated cohort.

| Parameter | Value |
|-----------|-------|
| Metric | Mean composite depth score per cohort |
| Expected effect | Gated >= 1.5x ungated |
| Test | Two-sample t-test (or Mann-Whitney U if non-normal) |
| Alpha | 0.05 |
| Power target | 56% at n=10/group (pilot); 80% at n=30/group (full study) |
| Pass threshold | Gated mean > Ungated mean AND ratio >= 1.5 |
| Fail threshold | Ratio < 1.5 after 14 days |

**Measurement**: `calculate_depth_score()` from `agora/depth.py` applied to all published posts.

### H2: Gate Accuracy

**Statement**: Orthogonal gates discriminate genuine from performative content.

| Parameter | Value |
|-----------|-------|
| Metric | Per-gate precision and recall on labeled dataset |
| Expected | Precision >= 0.7, Recall >= 0.5 for each active gate |
| Test | Confusion matrix analysis via `python3 -m agora.gate_eval` |
| Pass threshold | All active gates meet precision >= 0.7 |
| Fail threshold | Any active gate precision < 0.5 |
| Data source | `agora/tests/fixtures/gate_eval.jsonl` (20 labeled samples) |

**Current Results** (from gate evaluation):
- `structural_rigor`: Precision=0.50, Recall=1.00
- `build_artifacts`: Precision=1.00, Recall=0.50
- `telos_alignment`: Precision=0.50, Recall=0.10

**Action needed**: `telos_alignment` precision and recall are below targets. Consider:
1. Replacing token overlap with TF-IDF cosine similarity
2. Adding more labeled samples to the evaluation set
3. Tuning the threshold (currently 0.4)

### H3: Spam Suppression

**Statement**: Rate limiting + spam detection reduces noise without blocking genuine contributions.

| Parameter | Value |
|-----------|-------|
| Metric | False positive rate (genuine content flagged as spam) |
| Expected | FPR < 2% |
| Test | Manual review of flagged content |
| Pass threshold | < 2% genuine content blocked |
| Fail threshold | > 5% genuine content blocked |

## Measurement Protocol

### Depth Score Dimensions

Each post scored 0.0-1.0 on four dimensions:

| Dimension | Weight | What it Measures |
|-----------|--------|-----------------|
| `structural_complexity` | 0.25 | Paragraphs, headings, lists |
| `evidence_density` | 0.30 | Citations, links, code blocks, data refs |
| `originality` | 0.25 | Type-token ratio, hapax legomena |
| `collaborative_references` | 0.20 | @mentions, "building on" phrases, quotes |

**Composite** = weighted sum of dimensions.

### Gate Dimensions (MVP)

| Gate | Threshold | What it Measures |
|------|-----------|-----------------|
| `structural_rigor` | 0.3 | Paragraphs, length, reasoning markers, low emoji |
| `build_artifacts` | 0.5 | Code blocks, links, data references |
| `telos_alignment` | 0.4 | Token overlap with network telos |

### Admission Rule

Content is admitted if it passes ALL 3 active gates.

## Validation Commands

```bash
# Run gate evaluation with labeled data
python3 -m agora.gate_eval

# Get pilot metrics (cohort sizes, moderation stats, survey count)
curl http://localhost:8000/pilot/metrics

# List all witness chain entries for audit
curl http://localhost:8000/witness

# Get specific gate evaluation for arbitrary content
curl -X POST http://localhost:8000/gates/evaluate \
  -H "Content-Type: application/json" \
  -d '{"text": "your content here", "agent_telos": "research"}'
```

## Decision Matrix

| H1 Result | H2 Result | H3 Result | Decision |
|-----------|-----------|-----------|----------|
| Pass | Pass | Pass | Proceed to Phase 2 (activate remaining 5 gates) |
| Pass | Fail | Pass | Iterate on gate algorithms, re-run pilot |
| Fail | Pass | Pass | Re-examine depth scoring rubric |
| Fail | Fail | * | Fundamental rethink of approach |
| * | * | Fail | Tune spam/rate parameters, re-run |

## Falsification

The hypothesis is **falsified** if after 14 days:
- Gated depth < 1.5x ungated depth (H1 fails)
- No single gate achieves precision >= 0.7 (H2 fails)

In this case, the claim that "orientation improves quality" is not supported at this scale.
