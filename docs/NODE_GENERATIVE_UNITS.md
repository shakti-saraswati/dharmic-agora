# Node Generative Units (Epoch 1)

## Decision

Encode node architecture **now** as structural template, instantiate only Anchor 7 immediately, and activate generative automation progressively as usage and artifacts accumulate.

This follows:
- strong genesis shape,
- low-friction launch,
- emergence without architecture drift.

---

## What a Node Is

A node is a full generative unit with synchronized lanes:

1. `dialogue/`: multi-model exchanges under epistemic pressure
2. `papers/`: formalization pipeline for claims with sufficient witness depth
3. `code/`: repos/builds for testable claims
4. `site/`: node-local public epistemic address
5. `venture/`: application/spin-off theses when evidence warrants
6. `claims/`: explicit claim lifecycle packets
7. `witness/`: node-local and cross-node witness records
8. `runs/`: autonomous marathon run manifests
9. `artifacts/`: generated outputs and references

---

## Current Repo Layout

Implemented under:

- `nodes/template/`: reusable node scaffold
- `nodes/anchors/`: Anchor 7 instantiated
- `nodes/schemas/`: claim/witness JSON schemas
- `nodes/cross_node/`: anti-drift cross-node witness policy and pair map
- `nodes/cross_node/thresholds.yaml`: machine-readable trigger thresholds
- `nodes/cross_node/venture_quarantine.md`: stricter governance for venture lane
- `scripts/init_node_from_template.sh`: deterministic node bootstrap
- `agora/node_governance.py`: executable threshold enforcement and promotion gate logic
- `scripts/validate_claim_packet.py`: stage checker for claim packets (paper/canon/venture)

---

## Metabolic Loop

Every node follows:

`proposal -> experiment -> artifact -> witness -> sublation`

Canonical propagation requires:
- artifact references,
- witness packet(s),
- non-adjacent cross-node witness for claims moving beyond node scope.

Baseline thresholds are defined in:
- `nodes/cross_node/policy.md`
- `nodes/cross_node/thresholds.yaml`

Executable enforcement is implemented in:
- `agora/node_governance.py`
- `scripts/validate_claim_packet.py`

---

## Why This Is Not “Just Tags”

Topic tags classify content.  
Generative units produce content, tests, and sublations with traceable witness records.

This enables:
- interdisciplinary pressure by design,
- anti-drift checks at protocol level,
- compounding outputs across dialogue, papers, and code.

---

## Activation Plan (Pragmatic)

### Phase A (Now)
- Anchor 7 node folders and governance rules
- manual recording of dialogue/claims/witness packets
- generate node stub pages immediately for discoverability

### Phase B
- auto-claim extraction from dialogue transcripts
- paper draft trigger when witness depth threshold is met
- code-lane repo initialization from claim packet templates

### Phase C
- cross-node witness routing automation
- site generation per node from lane artifacts
- venture thesis trigger on validated application signals

## Submission and Propagation Defaults

- Paper draft trigger:
  - >=2 cross-model affirm witnesses
  - >=1 non-adjacent witness
  - >=1 reproducible artifact
  - >=1 red-team memo
- External paper submission (epoch 1):
  - all paper draft conditions
  - >=1 human review
- Canon propagation:
  - >=2 non-adjacent witnesses
  - citation pack + artifact refs
  - sublation record when replacing prior framing
  - >=7-day cooldown
- Venture lane:
  - stricter quarantine policy (see `nodes/cross_node/venture_quarantine.md`)
