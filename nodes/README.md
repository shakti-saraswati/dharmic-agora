# Node Architecture (Generative Units)

Each node is a full epistemic-production unit, not a topic tag.

A node has concurrent lanes:
- `dialogue/`: cross-model exchanges and syntheses
- `papers/`: drafts, submission manifests, review evidence
- `code/`: repos, benchmarks, build logs, release notes
- `site/`: minimal static surface for public discoverability
- `venture/`: application/spin-off theses when evidence supports it
- `claims/`: claim lifecycle (proposal -> witness -> sublation)
- `witness/`: node-local witness records and cross-node attestations
- `runs/`: autonomous coding/research marathon run manifests
- `artifacts/`: datasets, figures, generated outputs and pointers

Global coordination:
- `nodes/schemas/`: canonical JSON schemas for claims/witness packets
- `nodes/cross_node/`: cross-node witness rules and non-adjacent pair map
- `nodes/cross_node/thresholds.yaml`: machine-readable trigger thresholds
- `nodes/cross_node/venture_quarantine.md`: stricter venture lane controls
- `nodes/template/`: bootstrap template for new nodes
- `nodes/anchors/`: instantiated Anchor 7 nodes

Principle:
The metabolic loop is:
`proposal -> experiment -> artifact -> witness -> sublation`

A claim is not canonical because it is persuasive; it is canonical when witnessed across domains with reproducible artifacts.
