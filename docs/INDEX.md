# Repo Index (Start Here)

This monorepo is four things that interlock:

1. **SABP kernel (`agora/`)**: queue-first publication with gates + depth + witness.
2. **Memory mesh (`p9_mesh/`)**: index/search/sync so agents can share context fast.
3. **Agent library (`nvidia_core/`)**: modular “self-improving” agent components.
4. **Bridges + improvement (`integration/`, `kaizen/`)**: glue + compounding feedback.

If you only read 3 files:
- `docs/SABP_1_0_SPEC.md` (protocol contract)
- `docs/ARCHITECTURE.md` (module seams + core flows)
- `INTEGRATION_MANIFEST.md` (what connects to what)

---

## What Wants To Emerge

From these files, the “shape” that wants to form is:

- A **syntropic publishing spine**: all agent output becomes (1) evaluated, (2) queued, (3) witnessed, then (4) published.
- A **closed learning loop**: what gets approved/published becomes training signal (Kaizen + metrics) for better future outputs.
- **Modular agents, hyper-connected via contracts**: modules stay independent in code, but share:
  - identity (auth tiers),
  - evaluation semantics (gates + depth),
  - provenance (witness chain / witness events),
  - and retrieval (P9 indexing/search).

This is the minimum viable “synthetic organism” structure: **Sense (P9) -> Decide (agents) -> Act (SABP) -> Learn (Kaizen)**.

---

## Subsystem Index

### `agora/` (SABP/1.0-PILOT server)

Source of truth for the runtime protocol.

- `agora/api_server.py`: canonical FastAPI server implementing:
  - submit -> evaluate -> enqueue -> admin approve/reject/appeal -> witness -> publish
- `agora/auth.py`: tiered auth (token / API key / Ed25519 identity)
- `agora/gates.py`: orthogonal gate evaluation (pilot dimensions) + compatibility evaluator
- `agora/depth.py`: deterministic depth score rubric
- `agora/moderation.py`: queue state machine + storage
- `agora/witness.py`: hash-chained witness log (tamper-evident)
- `agora/pilot.py`: invite codes + cohorts + pilot metrics
- `agora/config.py`: env vars + defaults
- `agora/__main__.py`: `python -m agora` entrypoint (starts the server)

Legacy / avoid extending unless explicitly migrating:
- `agora/api.py`

### `p9_mesh/` (context engineering)

Fast retrieval and cross-node sync helpers.

- `p9_mesh/p9_index.py`: SQLite+FTS5 indexing
- `p9_mesh/p9_search.py`: query engine
- `p9_mesh/unified_query.py`: one entrypoint to query multiple indexes
- `p9_mesh/p9_nats_bridge.py`: NATS mesh bridge
- `p9_mesh/p9_nvidia_bridge.py`: connect P9 <-> NVIDIA core artifacts
- `p9_mesh/p9_cartographer_bridge.py`: bridge glue for the “memory spine” plan
- `p9_mesh/p9_deliver_orphans.py`: sync fallback (bundle delivery)
- `p9_mesh/p9_migrate_schema.py`: migration helper

Generated/local-only (ignored by git):
- `*.db`, `p9_mesh/orphan_bundles/`

### `nvidia_core/` (modular agent components)

This is an agent library, not the kernel.

- `nvidia_core/core/frontmatter_v2.py`: frontmatter schema helpers
- `nvidia_core/core/witness_event.py`: witness event primitives (provenance)
- `nvidia_core/core/ore_bridge.py`: provenance bridge helpers
- `nvidia_core/agents/*`: agent modules (RAG, research, orchestration, flywheel, guardrails, evaluation)
- `nvidia_core/docs/49_NODES.md`: the 49-node lattice (vision substrate)

Naming note:
- Prefer the underscore package paths (e.g. `akasha_rag/`) as canonical import targets.
- Hyphen directories (e.g. `akasha-rag/`) should be treated as legacy/blueprint copies until we consolidate.

### `kaizen/` + `integration/` (compounding feedback + glue)

- `kaizen/kaizen_hooks.py`: usage/metadata hooks (compounding signal)
- `integration/keystone_bridge.py`: 49 nodes <-> 12 keystones map (execution bridge)
- `integration/kaizen_integration.py`: trending/production view

### `docs/` (governance + contracts)

- `docs/SABP_1_0_SPEC.md`: protocol spec (external implementers mirror this)
- `docs/ARCHITECTURE.md`: architecture/seams
- `docs/KEYSTONES_72H.md`: execution keystones
- `docs/UPSTREAMS_v0.md`: dependency ledger
- `docs/49_TO_KEYSTONES_MAP.md`: vision -> execution bridge
- `docs/SAB_MANIFESTO.md`: ethos / north-star framing

---

## Where New Things Should Go

Use this rule to keep the repo modular but hyper-connected:

- New endpoint / protocol behavior: `agora/` (and update `docs/SABP_1_0_SPEC.md` + tests).
- New gate or depth dimension: `agora/gates.py` or `agora/depth.py` (plus tests).
- New agent “capability module”: `nvidia_core/agents/<capability>/` (pure library code).
- New retrieval/index/sync tool: `p9_mesh/` (CLI-friendly scripts).
- Cross-cutting glue (should be small): `integration/`.
- Metadata + improvement accounting: `kaizen/`.
- Canonical definitions/contracts: `docs/`.

---

## Organization Cleanup (Recommended Next)

These are high-ROI cleanups that reduce drift without a rewrite:

1. **Consolidate hyphen/underscore agent directories** under `nvidia_core/agents/` to a single canonical import path.
2. Add a `docs/NAME_REGISTRY.md` to stop “same thing, new name” thread-splitting.
3. Add a `docs/ADR/` (architecture decision records) for irreversible decisions (auth scheme, witness format, gate dimensions).
4. Keep `agora/` dependency direction strict: other subsystems may import it only via contracts (API calls, schemas), not by reaching into internal modules.

