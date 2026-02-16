# Name Registry

This file exists to stop thread-splitting:
"same thing, new name" -> duplicated effort -> drift.

Rule:
- If a name is going to live longer than 24 hours (a module, protocol, product, repo, agent, or OS),
  it must have a registry entry here.

The registry is intentionally machine-checkable.

---

## Registry (YAML)

```yaml
version: 1
entries:
  - key: dharmic_agora
    canonical: DHARMIC_AGORA
    aliases:
      - agora (repo)
    scope: repo
    notes: "Unified monorepo: SABP kernel + agent_core + p9_mesh + kaizen + integration."

  - key: sabp
    canonical: SABP
    aliases:
      - Syntropic Attractor Basin Protocol
      - Synthetic Attractor Basin Protocol
      - SABP/1.0
      - SABP/1.0-PILOT
    scope: protocol
    notes: "Queue-first publishing protocol: gates + depth + witness."

  - key: sab
    canonical: SAB
    aliases:
      - Synthetic Attractor Bridge
    scope: product
    notes: "Product layer (future): a consciousness-first coding environment built on SABP + shared memory."

  - key: agent_core
    canonical: agent_core
    aliases:
      - nvidia_core (legacy)
      - nvidia power repo (legacy)
    scope: code
    notes: "Modular capability library (RAG/research/orchestration/flywheel/guardrails/eval)."

  - key: p9_mesh
    canonical: p9_mesh
    aliases:
      - P9
      - context engineering mesh
    scope: code
    notes: "Index/search/sync utilities for shared context."

  - key: kaizen_os
    canonical: Kaizen OS
    aliases:
      - kaizen
      - kaizen layer
    scope: concept
    notes: "Continuous improvement hooks (usage/trending/archival signals)."

  - key: factory_os
    canonical: Factory OS
    aliases:
      - MKK_改善工場_OS
      - 改善工場OS
      - koujou os
      - koujou (factory)
    scope: concept
    notes: "If you see variants, treat them as aliases of Factory OS unless explicitly split by registry."

  - key: hyperbolic_chamber
    canonical: Hyperbolic Chamber
    aliases:
      - 49-node lattice
      - Indra's Net
      - 7x7 lattice
    scope: document
    notes: "500-year debate substrate that seeds execution via keystone bridges."
```

---

## Process

When you introduce a new name:
1. Add an entry above.
2. Pick a stable `key` (snake_case).
3. List known aliases (including your own typos if they are recurring).
